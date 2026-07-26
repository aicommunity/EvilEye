import numpy as np

from evileye.object_tracker.object_tracking_botsort import ObjectTrackingBotsort


def test_parse_det_info_accepts_inference_dto_dict():
    tracker = ObjectTrackingBotsort.__new__(ObjectTrackingBotsort)
    det_info = {
        "source_id": 5,
        "frame_id": 42,
        "detections": [
            {"bbox_xyxy": [10, 20, 30, 40], "confidence": 0.8, "class_id": 1},
        ],
    }
    image = np.zeros((100, 200, 3), dtype=np.uint8)

    cam_id, boxes = tracker._parse_det_info(det_info, image)
    assert cam_id == 5
    assert boxes.data.shape[0] == 1
