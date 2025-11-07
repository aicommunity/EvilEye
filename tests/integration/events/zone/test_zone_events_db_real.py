import os
import time
import json
import shutil
import tempfile
from datetime import datetime

import numpy as np
import pytest

from evileye.database_controller.database_controller_pg import DatabaseControllerPg
from evileye.database_controller.db_adapter_zone_events import DatabaseAdapterZoneEvents
from evileye.events_detectors.zone import Zone
from evileye.events_detectors.event_zone import ZoneEvent


class DummyTrack:
    def __init__(self, box):
        self.bounding_box = box


class DummyLastImage:
    def __init__(self, w=640, h=480):
        self.image = np.zeros((h, w, 3), dtype=np.uint8)


class DummyObj:
    def __init__(self, source_id, object_id, box):
        self.source_id = source_id
        self.object_id = object_id
        self.track = DummyTrack(box)
        self.last_image = DummyLastImage()
        self.time_stamp = datetime.now()


def _load_db_config():
    cfg_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'evileye', 'database_config.json')
    # Fallback to project root config path
    if not os.path.exists(cfg_path):
        cfg_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'evileye', 'database_config.json')
    with open(cfg_path, 'r') as f:
        return json.load(f)


@pytest.mark.integration
def test_zone_events_real_db_insert_update():
    db_conf = _load_db_config()
    db_params = db_conf['database']
    adapters = db_conf.get('database_adapters', {})

    # Prepare temp image dir to avoid polluting real data folder
    tempdir = tempfile.mkdtemp(prefix='ee_zone_events_real_')
    db_params = dict(db_params)
    db_params['image_dir'] = tempdir

    # Provide required connection params if missing
    db_params.setdefault('user_name', 'postgres')
    db_params.setdefault('password', '')
    db_params.setdefault('host_name', 'localhost')
    db_params.setdefault('port', 5432)
    db_params.setdefault('admin_user_name', 'postgres')
    db_params.setdefault('admin_password', '')

    # Minimal system params for controller
    system_params = {
        'pipeline': {
            'sources': []
        }
    }

    db = DatabaseControllerPg(system_params)
    db.set_params(**{
        'user_name': db_params['user_name'],
        'password': db_params['password'],
        'database_name': db_params.get('database_name', 'evil_eye_db'),
        'host_name': db_params['host_name'],
        'port': db_params['port'],
        'admin_user_name': db_params['admin_user_name'],
        'admin_password': db_params['admin_password'],
        'image_dir': db_params['image_dir'],
        'create_new_project': db_params.get('create_new_project', False),
        'tables': db_params['tables'],
        'preview_width': db_params.get('preview_width', 300),
        'preview_height': db_params.get('preview_height', 150),
    })

    try:
        try:
            db.init()
            db.connect()
        except Exception as e:
            pytest.skip(f"Database not available: {e}")

        adapter_conf = adapters.get('DatabaseAdapterZoneEvents', {'table_name': 'zone_events', 'event_name': 'ZoneEvent'})
        adapter = DatabaseAdapterZoneEvents(db)
        adapter.set_params(**adapter_conf)
        adapter.init()
        adapter.start()

        # Create and insert zone event
        zone = Zone(2, [(0.3, 0.6), (0.7, 0.6), (0.7, 0.9), (0.3, 0.9)], 'poly', is_active=True)
        zone.set_id(10)
        obj_enter = DummyObj(source_id=2, object_id=9999, box=[100, 200, 300, 350])
        ev_enter = ZoneEvent(timestamp=obj_enter.time_stamp, alarm_type='Alarm', obj=obj_enter, zone=zone, is_finished=False)
        ev_enter.event_id = int(datetime.now().timestamp())  # unique id

        adapter.insert(ev_enter)
        time.sleep(0.2)

        # Verify insert by selecting the event id directly
        from psycopg2 import sql
        select_q = sql.SQL('SELECT event_id, source_id, object_id, time_entered FROM zone_events WHERE event_id = %s')
        recs = db.query(select_q, (ev_enter.event_id,))
        assert recs and recs[0][0] == ev_enter.event_id

        # Update (leaving event)
        obj_left = DummyObj(source_id=2, object_id=9999, box=[120, 210, 320, 360])
        ev_left = ZoneEvent(timestamp=obj_left.time_stamp, alarm_type='Alarm', obj=obj_left, zone=zone, is_finished=True)
        ev_left.event_id = ev_enter.event_id
        adapter.update(ev_left)
        time.sleep(0.2)

        # Verify update has time_left set
        select_q2 = sql.SQL('SELECT time_left, box_left FROM zone_events WHERE event_id = %s')
        recs2 = db.query(select_q2, (ev_enter.event_id,))
        assert recs2 and recs2[0][0] is not None

        adapter.stop()
    finally:
        try:
            db.disconnect()
        except Exception:
            pass
        shutil.rmtree(tempdir, ignore_errors=True)
