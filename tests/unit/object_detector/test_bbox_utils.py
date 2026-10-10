import numpy as np

from evileye.object_detector.bbox_utils import roi_boxes_to_image_coords


class _Boxes:
    def __init__(self, coords=((1.0, 2.0, 3.0, 4.0),)):
        self.coords = coords

    def cpu(self):
        return self

    def numpy(self):
        obj = type("Arr", (), {})()
        obj.xyxy = np.array(self.coords, dtype=np.float32)
        obj.conf = np.array([0.9] * len(self.coords), dtype=np.float32)
        obj.cls = np.array([2.0] * len(self.coords), dtype=np.float32)
        return obj


class _Result:
    def __init__(self, coords=((1.0, 2.0, 3.0, 4.0),), shape=None):
        self.boxes = _Boxes(coords)
        if shape is not None:
            self.orig_img = np.zeros(shape, dtype=np.uint8)


def test_roi_boxes_to_image_coords_truncates_by_default():
    roi = [None, [10, 20]]
    boxes, confidences, ids = roi_boxes_to_image_coords(
        _Result(), (roi[1][0], roi[1][1])
    )
    assert boxes == [[11, 22, 13, 24]]
    assert np.isclose(confidences[0], 0.9)
    assert ids[0] == 2.0


def test_roi_boxes_can_match_legacy_rtdetr_rounding_and_clipping():
    result = _Result(coords=((1.6, 2.4, 9.8, 10.1),), shape=(10, 10, 3))
    boxes, _, _ = roi_boxes_to_image_coords(
        result, (10, 20), round_coordinates=True, clip_to_image=True
    )
    assert boxes == [[12, 22, 19, 29]]
