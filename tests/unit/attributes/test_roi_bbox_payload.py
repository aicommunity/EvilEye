import numpy as np

from evileye.attributes_detection.roi_feeder import RoiFeeder
from evileye.attributes_detection.mp_worker_attributes import MpWorkerAttributeClassifier


class _Track:
    def __init__(self, track_id=1, bbox=(1, 1, 6, 6), class_id=0):
        self.track_id = track_id
        self.bounding_box = bbox
        self.class_id = class_id


class _TrackingData:
    def __init__(self):
        self.tracks = [_Track()]


class _Frame:
    def __init__(self):
        self.image = np.zeros((10, 10, 3), dtype=np.uint8)
        self.source_id = 0
        self.frame_id = 1


def test_roi_feeder_stores_bbox_instead_of_image():
    feeder = RoiFeeder()
    tracking = _TrackingData()
    frame = _Frame()

    feeder._extract_rois(tracking, frame)
    assert hasattr(tracking, "roi_data")
    assert "roi_bbox" in tracking.roi_data[0]
    assert "roi_image" not in tracking.roi_data[0]


def test_attribute_worker_crops_from_bbox():
    worker = MpWorkerAttributeClassifier(input_queue=None, output_queue=None)
    frame = _Frame()
    roi = worker._crop_roi(frame.image, [1, 1, 6, 6])
    assert roi is not None
    assert roi.shape[0] == 5
    assert roi.shape[1] == 5
