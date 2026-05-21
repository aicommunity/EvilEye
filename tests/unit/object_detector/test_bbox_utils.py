import numpy as np

from evileye.object_detector.bbox_utils import roi_boxes_to_image_coords


class _Boxes:
    def cpu(self):
        return self

    def numpy(self):
        obj = type("Arr", (), {})()
        obj.xyxy = np.array([[1.0, 2.0, 3.0, 4.0]], dtype=np.float32)
        obj.conf = np.array([0.9], dtype=np.float32)
        obj.cls = np.array([2.0], dtype=np.float32)
        return obj


class _Result:
    def __init__(self):
        self.boxes = _Boxes()


def test_roi_boxes_to_image_coords():
    roi = [None, [10, 20]]
    bboxes, confs, ids = roi_boxes_to_image_coords(_Result(), (roi[1][0], roi[1][1]))
    assert len(bboxes) == 1
    assert bboxes[0] == [11, 22, 13, 24]
    assert confs[0] == 0.9
    assert ids[0] == 2.0
