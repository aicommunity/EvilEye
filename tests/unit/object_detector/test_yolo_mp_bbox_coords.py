import numpy as np

from evileye.core.frame import Frame
from evileye.object_detector.bbox_utils import (
    clip_xyxy_list,
    mp_dict_list_to_image_coords,
    roi_boxes_to_image_coords
)


class _FakeBoxes:
    def __init__(self, xyxy, conf, cls):
        self.xyxy = xyxy
        self.conf = conf
        self.cls = cls

    def numpy(self):
        return self


class _FakeResult:
    def __init__(self):
        self.boxes = _FakeBoxes(
            np.array([[10.0, 20.0, 30.0, 40.0]]),
            np.array([0.9]),
            np.array([0]),
        )


def test_mp_dict_list_matches_roi_offset():
    result = [
        {"bbox_xyxy": [10.0, 20.0, 30.0, 40.0], "confidence": 0.9, "class_id": 0},
    ]
    mp_boxes, _, _ = mp_dict_list_to_image_coords(result, (100, 200))
    ul_boxes, _, _ = roi_boxes_to_image_coords(_FakeResult(), (100, 200))
    assert len(mp_boxes) == 1
    assert len(ul_boxes) == 1
    assert np.allclose(mp_boxes[0], ul_boxes[0])


def test_clip_xyxy_list():
    boxes = [[-5, -5, 200, 200]]
    clipped = clip_xyxy_list(boxes, 100, 80)
    assert len(clipped) == 1
    assert clipped[0][0] >= 0
    assert clipped[0][2] <= 99
    assert clipped[0][3] <= 79


def test_non_finite_dict_bbox_filtered():
    result = [{"bbox_xyxy": [float("nan"), 1, 2, 3], "confidence": 0.5, "class_id": 0}]
    boxes, confs, ids = mp_dict_list_to_image_coords(result, (0, 0))
    assert boxes == []
    assert confs == []
    assert ids == []
