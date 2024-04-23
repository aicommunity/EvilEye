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
     
    is_actual = True

    det_info = {
        'cam_id': 0,
        'objects': [
            {'bbox': [1, 2, 10, 10], 'conf': 0.8, 'class': 0}
        ]
    }

    tracker = ObjectTrackingBotsort()
    track_info = tracker.process(det_info, is_actual)
    
    assert track_info['cam_id'] == det_info['cam_id']
    assert pytest.approx(track_info['objects'][0]['bbox']) == det_info['objects'][0]['bbox']
    assert pytest.approx(track_info['objects'][0]['conf']) == det_info['objects'][0]['conf']
    assert int(track_info['objects'][0]['class']) == det_info['objects'][0]['class']
    assert int(track_info['objects'][0]['track_id']) == 0


if __name__ == '__main__':
    sys.exit(pytest.main([__file__]))
