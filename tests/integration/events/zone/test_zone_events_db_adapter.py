import os
import time
import shutil
import tempfile
from datetime import datetime

import numpy as np

from evileye.events_detectors.event_zone import ZoneEvent
from evileye.events_detectors.zone import Zone
from evileye.database_controller.db_adapter_zone_events import DatabaseAdapterZoneEvents


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


class DummyDbController:
    def __init__(self, base_dir):
        self._params = {
            'image_dir': base_dir,
            'preview_width': 300,
            'preview_height': 150,
        }
        self._queries = []
        self._last_zone_coords = None

    def get_params(self):
        return self._params

    def get_cameras_params(self):
        return {}

    def get_project_id(self):
        return 1

    def get_job_id(self):
        return 1

    def query(self, query, data):
        # Record query and return dummy RETURNING row
        self._queries.append((query, data))
        # Emulate RETURNING box and zone
        # box_entered/box_left and zone_coords depending on operation
        if 'INSERT' in str(query):
            # fields order from _prepare_for_saving():
            # box_entered at index 5, zone_coords at index 7
            self._last_zone_coords = data[7]
            return [[data[5], data[7]]]  # box_entered, zone_coords
        else:
            # For update, data[0] is box_left; reuse stored zone_coords
            return [[data[0], self._last_zone_coords]]  # box_left, zone_coords


def test_zone_events_db_adapter_insert_and_update():
    tempdir = tempfile.mkdtemp(prefix='ee_zone_events_')
    try:
        db = DummyDbController(tempdir)
        adapter = DatabaseAdapterZoneEvents(db)
        adapter.set_params(table_name='zone_events', event_name='ZoneEvent')
        adapter.init()
        adapter.start()

        # Build entering event
        zone = Zone(2, [(0.3, 0.6), (0.7, 0.6), (0.7, 0.9), (0.3, 0.9)], 'poly', is_active=True)
        zone.set_id(10)
        obj = DummyObj(source_id=2, object_id=5, box=[100, 200, 300, 350])
        enter_event = ZoneEvent(timestamp=obj.time_stamp, alarm_type='Alarm', obj=obj, zone=zone, is_finished=False)
        enter_event.event_id = 123

        # Queue insert
        adapter.insert(enter_event)
        time.sleep(0.1)

        # Build leaving event for update
        obj_left = DummyObj(source_id=2, object_id=5, box=[120, 220, 310, 360])
        leave_event = ZoneEvent(timestamp=obj_left.time_stamp, alarm_type='Alarm', obj=obj_left, zone=zone, is_finished=True)
        leave_event.event_id = 123

        adapter.update(leave_event)
        time.sleep(0.1)

        adapter.stop()

        # Validate queries executed
        assert len(db._queries) >= 2, 'DB queries for insert and update must be executed'

        # Validate images saved
        assert os.path.isdir(os.path.join(tempdir, 'images')), 'Images directory should be created'
    finally:
        shutil.rmtree(tempdir, ignore_errors=True)
