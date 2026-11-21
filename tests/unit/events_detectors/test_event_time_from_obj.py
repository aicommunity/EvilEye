from datetime import datetime

from evileye.core.event_time import obj_found_datetime, obj_lost_datetime
from evileye.events_detectors.event_attribute import AttributeEvent
from evileye.events_detectors.event_fov import FieldOfViewEvent
from evileye.events_detectors.event_zone import ZoneEvent
from evileye.objects_handler.object_result import ObjectResult


class _Zone:
    def get_zone_id(self):
        return 1

    def get_coords(self):
        return [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]


class _Track:
    bounding_box = [0, 0, 10, 10]


def _obj(*, stamp, lost=None):
    obj = ObjectResult()
    obj.source_id = 0
    obj.object_id = 42
    obj.time_stamp = stamp
    obj.time_detected = stamp
    obj.time_lost = lost
    obj.track = _Track()
    obj.last_image = None
    return obj


def test_fov_event_uses_object_timestamp():
    stamp = datetime(2026, 8, 17, 10, 0, 0)
    obj = _obj(stamp=stamp)
    event = FieldOfViewEvent(obj_found_datetime(obj), "Alarm", obj)
    assert event.timestamp == stamp
    assert event.time_obj_detected == stamp


def test_fov_finished_uses_lost_timestamp():
    stamp = datetime(2026, 8, 17, 10, 0, 0)
    lost = datetime(2026, 8, 17, 10, 0, 3)
    obj = _obj(stamp=stamp, lost=lost)
    event = FieldOfViewEvent(obj_lost_datetime(obj), "Alarm", obj, is_finished=True)
    assert event.timestamp == lost
    assert event.time_lost == lost


def test_zone_event_uses_history_timestamp_not_current_obj():
    hist = datetime(2026, 8, 17, 10, 0, 0)
    current = datetime(2026, 8, 17, 10, 0, 5)
    obj = _obj(stamp=current)
    event = ZoneEvent(hist, "Alarm", obj, _Zone())
    assert event.timestamp == hist
    assert event.time_entered == hist


def test_attribute_event_uses_object_timestamp():
    stamp = datetime(2026, 8, 17, 10, 0, 0)
    obj = _obj(stamp=stamp)
    event = AttributeEvent(
        obj_found_datetime(obj),
        "AttributeEvent",
        0,
        obj.object_id,
        "hard_hat",
        ["hard_hat"],
        obj=obj,
    )
    assert event.timestamp == stamp
    assert event.time_found == stamp
