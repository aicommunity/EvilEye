"""Exercise production zone rules against an isolated PostgreSQL database and JSON journal.

The database must already contain a copy of the deployment schema. No writes are
made to the deployment database or media directory.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace as S

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class Handler:
    def __init__(self):
        self.active = S(objects=[])
        self.lost = S(objects=[])
        self.subscribers = []

    def get(self, kind, source_id):
        return getattr(self, kind)

    def subscribe(self, *subscribers):
        self.subscribers.extend(subscribers)

    def notify(self):
        for subscriber in self.subscribers:
            subscriber.update()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, required=True)
    parser.add_argument('--database', required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args()
    cfg = json.loads((args.site/'configs/poly-cameras-gst.json').read_text())
    creds = json.loads((args.site/'credentials.json').read_text())['database']
    if not args.database.startswith('evileye_verify_') or args.database == creds['database_name']:
        raise ValueError('An isolated evileye_verify_* database is required')
    args.work_dir.mkdir(parents=True, exist_ok=True)
    from shapely.geometry import Polygon
    import numpy as np
    from evileye.controller.services.events_service import EventsService
    from evileye.database_controller.database_controller_pg import DatabaseControllerPg
    from evileye.database_controller.db_adapter_zone_events import DatabaseAdapterZoneEvents
    from evileye.database_controller.json_adapter_zone_events import JsonAdapterZoneEvents
    from evileye.database_controller.migrations import apply_startup_migrations
    from evileye.events_control.events_controller import EventsDetectorsController
    from evileye.events_control.events_processor import EventsProcessor
    from evileye.api.core import journal_service

    default = json.loads((Path(__file__).resolve().parents[1]/'evileye/database_config.json').read_text())['database']
    params = {**default, **creds, 'database_name': args.database,
              'image_dir': str(args.work_dir), 'preview_width': 300, 'preview_height': 150}
    params.setdefault('create_new_project', False)
    database = DatabaseControllerPg(cfg)
    database.set_params(**params)
    database.init()
    database.connect()
    assert database.is_connected()
    apply_startup_migrations(database)
    pg = DatabaseAdapterZoneEvents(database)
    pg.set_params(table_name='zone_events', event_name='ZoneEvent')
    js = JsonAdapterZoneEvents(database)
    js.set_params(image_dir=str(args.work_dir))
    for adapter in (pg, js):
        adapter.init()
        adapter.start()
    processor = EventsProcessor([pg, js], database)
    processor.init()
    service, collector = EventsService(), None
    try:
        zone_cfg = cfg['events_detectors']['ZoneEventsDetector']
        source_id = next(int(k) for k, zones in zone_cfg['sources'].items() if zones)
        coords = zone_cfg['sources'][str(source_id)][0]
        point = Polygon(coords).representative_point()
        handler = Handler()
        pipeline = S(get_sources=lambda: [S(source_ids=[source_id])])
        service.initialize_detectors({'enabled': ['ZoneEventsDetector'], 'ZoneEventsDetector': {
            **zone_cfg, 'execution_mode': 'process'}}, pipeline, handler, use_database=False)
        service.start_detectors()
        detector = service.get_detector('ZoneEventsDetector')
        collector = EventsDetectorsController([detector])
        collector.init()
        collector.start()
        processor.start()
        base = datetime.now()-timedelta(seconds=10)
        image = S(source_id=source_id, frame_id=4, time_stamp=base, image=np.zeros((1292,2304,3), dtype=np.uint8))
        def make_object(object_id, x, y):
            box = [x*2304-10, y*1292-30, x*2304+10, y*1292]
            history = [S(source_id=source_id, object_id=object_id, global_id=object_id,
                         class_id=0, frame_id=i, time_stamp=base+timedelta(seconds=i),
                         time_detected=base, time_lost=None, track=S(bounding_box=box))
                       for i in range(5)]
            return S(**{**vars(history[-1]), 'history': history, 'last_image': image, 'attributes': {}})
        positive = make_object(900000001, point.x, point.y)
        def deliver(expected):
            deadline = time.monotonic()+10
            delivered = []
            while time.monotonic() < deadline:
                batch = collector.get()
                if batch:
                    delivered.extend(batch.get('ZoneEventsDetector', []))
                    processor.put(batch)
                if len(delivered) >= expected:
                    return delivered
                time.sleep(.02)
            return delivered
        handler.active.objects = [positive]
        handler.notify()
        assert len(deliver(1)) == 1, 'entry was not delivered'
        positive.last_image = None
        positive.time_lost = base+timedelta(seconds=6)
        handler.active.objects = []
        handler.lost.objects = [positive]
        handler.notify()
        assert len(deliver(1)) == 1, 'exit was not delivered'
        handler.lost.objects = []
        handler.active.objects = [make_object(900000002, .99, .99)]
        handler.notify()
        assert deliver(1) == [], 'negative scenario generated an event'
        deadline = time.monotonic()+10
        while time.monotonic() < deadline:
            rows = database.query_checked('SELECT time_entered,time_left FROM zone_events WHERE object_id=%s', (positive.object_id,))
            if rows and rows[-1][1] is not None:
                break
            time.sleep(.05)
        assert rows and rows[-1][0] and rows[-1][1], 'PostgreSQL entry/exit is incomplete'
        files = list(args.work_dir.glob('Events/*/Metadata/zone_events_*.json'))
        assert len(files) >= 2, 'JSON entry/exit files missing'
        assert list(args.work_dir.rglob('*.jpg')), 'event previews missing'
        # Exercise the same journal service used by the HTTP API, using the isolated DB.
        journal_service._db_controller_cache = database
        journal_service._db_controller_failed = False
        journal_service.configured_storage_mode = lambda: 'database'
        journal_service._use_json_journal = lambda: False
        journal_service._image_base_dir = lambda: str(args.work_dir)
        payload = journal_service.load_events_page(page=0, size=50, filters={}, date=base.strftime('%Y-%m-%d'))
        assert payload['available'] and payload['items'], 'API journal did not expose events'
        print(json.dumps({'ok': True, 'source_id': source_id, 'zone_events': len(rows),
                          'json_files': len(files), 'journal_rows': len(payload['items']),
                          'processor': processor.get_runtime_stats()}, default=str))
    finally:
        if collector is not None:
            collector.stop()
        processor.stop()
        service.release()
        for adapter in (pg, js):
            adapter.stop()
        database.disconnect()


if __name__ == '__main__':
    main()
