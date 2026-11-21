from __future__ import annotations

import datetime
import json

import numpy as np

from evileye.core.frame import Frame
from evileye.events_detectors.event_zone import LazyJpegFrame, _copy_frame_image
from evileye.utils.utils import ObjectResultEncoder, dumps_object_data, object_data_as_dict


def test_object_result_encoder_serializes_frame_as_null():
    payload = {
        "time_detected": datetime.datetime(2026, 9, 1, 12, 0, 0),
        "last_image": Frame(),
        "nested": {"image": Frame()},
    }
    encoded = json.loads(json.dumps(payload, cls=ObjectResultEncoder))
    assert encoded["time_detected"] == "2026-09-01T12:00:00"
    assert encoded["last_image"] is None
    assert encoded["nested"]["image"] is None


def test_object_result_encoder_serializes_lazy_jpeg_as_null():
    proxy = Frame()
    lazy = LazyJpegFrame(proxy, b"\xff\xd8\xff")
    encoded = json.loads(json.dumps({"sticky": lazy}, cls=ObjectResultEncoder))
    assert encoded["sticky"] is None


def test_dumps_object_data_excludes_sticky_and_survives_lazy_jpeg():
    class _Obj:
        def __init__(self):
            self.source_id = 1
            self.object_id = 7
            self.time_stamp = datetime.datetime(2026, 9, 1, 12, 0, 0)
            self.time_lost = None
            self.class_id = 0
            self.last_image = Frame()
            self._zone_event_sticky_image = LazyJpegFrame(Frame(), b"\xff\xd8\xff")
            self._zone_jpeg_bytes = b"secret"

    obj = _Obj()
    data = object_data_as_dict(obj)
    assert "_zone_event_sticky_image" not in data
    assert "_zone_jpeg_bytes" not in data
    encoded = json.loads(dumps_object_data(obj))
    assert encoded["object_id"] == 7
    assert "_zone_event_sticky_image" not in encoded
    assert encoded["last_image"] is None


def test_copy_frame_image_returns_module_level_lazy_jpeg():
    frame = Frame()
    frame.image = np.zeros((8, 8, 3), dtype=np.uint8)
    out = _copy_frame_image(frame)
    assert isinstance(out, LazyJpegFrame)
    assert out.image is not None
    assert out.image.shape == (8, 8, 3)
