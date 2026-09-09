from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from evileye.database_controller.db_adapter_zone_events import DatabaseAdapterZoneEvents
from evileye.events_detectors.event_zone import ZoneEvent
from evileye.events_detectors.zone import Zone


class _DummyDb:
    def get_params(self):
        return {
            "image_dir": "/tmp/evileye_test_images",
            "preview_width": 300,
            "preview_height": 150,
        }

    def get_cameras_params(self):
        return {}

    def get_project_id(self):
        return 1

    def get_job_id(self):
        return 1


def _zone():
    return Zone(0, [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)], "poly", is_active=True)


def test_prepare_for_saving_with_none_img_entered():
    adapter = DatabaseAdapterZoneEvents(_DummyDb())
    adapter.params = {"table_name": "zone_events", "event_name": "ZoneEvents"}
    adapter.set_params_impl()

    obj = SimpleNamespace(
        source_id=0,
        object_id=7,
        track=SimpleNamespace(bounding_box=[100, 200, 300, 400]),
        last_image=None,
        time_stamp=datetime(2026, 9, 9, 12, 0, 0),
        history=[],
    )
    event = ZoneEvent(obj.time_stamp, "Alarm", obj, _zone())
    assert event.img_entered is None

    fields, data, preview_path, frame_path = adapter._prepare_for_saving(event)
    assert "box_entered" in fields
    box = data[fields.index("box_entered")]
    assert box == [100 / 1920, 200 / 1080, 300 / 1920, 400 / 1080]
    assert preview_path
    assert frame_path


def test_insert_clears_img_entered_after_queue():
    adapter = DatabaseAdapterZoneEvents(_DummyDb())
    adapter.params = {"table_name": "zone_events", "event_name": "ZoneEvents"}
    adapter.set_params_impl()
    adapter.db_controller = MagicMock()
    adapter.db_controller.get_project_id.return_value = 1
    adapter.db_controller.get_job_id.return_value = 1
    adapter.db_controller.is_connected.return_value = True
    adapter.db_controller.get_params.return_value = _DummyDb().get_params()

    img = SimpleNamespace(image=np.zeros((480, 640, 3), dtype=np.uint8))
    obj = SimpleNamespace(
        source_id=0,
        object_id=1,
        track=SimpleNamespace(bounding_box=[1, 2, 3, 4]),
        last_image=img,
        time_stamp=datetime(2026, 9, 9, 12, 0, 0),
        history=[],
    )
    event = ZoneEvent(obj.time_stamp, "Alarm", obj, _zone())
    assert event.img_entered is not None

    adapter.insert(event)
    assert event.img_entered is None
    assert not adapter.queue_in.empty()
    item = adapter.queue_in.get_nowait()
    assert item[-1] is not None
