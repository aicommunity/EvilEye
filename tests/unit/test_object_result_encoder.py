from __future__ import annotations

import datetime
import json

from evileye.core.frame import Frame
from evileye.utils.utils import ObjectResultEncoder


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
