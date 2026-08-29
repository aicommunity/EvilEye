"""DetectionThreadBase ROI hot-reload updates roi_coords_per_camera."""

from queue import Queue

from evileye.object_detector.detection_thread_base import DetectionThreadBase


class _StubThread(DetectionThreadBase):
    def init_detection_implementation(self):
        return None

    def predict(self, image, split_image):
        return None

    def get_bboxes(self, result, roi):
        return [], [], []


def test_set_rois_for_source_refreshes_roi_coords_per_camera():
    thread = _StubThread(
        stride=1,
        classes=[0],
        source_ids=[0, 2],
        roi=[[[10, 10, 20, 20]], [[1, 2, 3, 4]]],
        inf_params={},
        queue_out=Queue(),
    )
    assert thread.roi_coords_per_camera[2] == [[1, 2, 3, 4]]

    thread.set_rois_for_source(2, [[100, 200, 50, 60]])
    assert thread.roi[1] == [[100, 200, 50, 60]]
    assert thread.roi_coords_per_camera[2] == [[100, 200, 50, 60]]
