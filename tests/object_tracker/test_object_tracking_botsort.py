import os
import sys
import pytest
import numpy as np
from pathlib import Path
from types import SimpleNamespace

sys.path.append(str(Path(__file__).parent.parent.parent))
from object_tracker.trackers.cfg.utils import read_cfg
from object_tracker.object_tracking_botsort import ObjectTrackingBotsort


def test_one_obj_one_frame():
    
    bboxes_coords_xyxy = np.array([[1, 2, 10, 10]])
    confidences = np.array([0.8])
    class_ids = np.array([0]) 
    is_actual = True

    tracker = ObjectTrackingBotsort()
    tracks = tracker.process(bboxes_coords_xyxy, confidences, class_ids, is_actual)
    track_bboxes_coords_xyxy, track_confidences, track_class_ids, track_ids = tracks

    assert (track_bboxes_coords_xyxy == bboxes_coords_xyxy).min()
    assert pytest.approx(track_confidences[0]) == confidences[0]
    assert pytest.approx(track_class_ids[0]) == class_ids[0]
    assert pytest.approx(track_ids[0]) == 0


if __name__ == '__main__':
    sys.exit(pytest.main([__file__]))
