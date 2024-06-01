import os
import sys
import pytest
import numpy as np
from pathlib import Path
from types import SimpleNamespace

sys.path.append(str(Path(__file__).parent.parent.parent.parent))
from object_tracker.trackers.cfg.utils import read_cfg
from object_tracker.trackers.bot_sort import BOTSORT


def test_botsort():
    cfg = read_cfg()
    tracker = BOTSORT(args=cfg, frame_rate=30)
    
    cls = np.array([0])
    xywh = np.array([[0.5, 0.5, 1., 1.]])
    conf = np.array([0.8])
    
    tracks = tracker.update(cls, xywh, conf, None)
    print(tracks)
    assert tracks.shape == (1, 8)
    assert tracks[0][0:4].tolist() == [0, 0, 1, 1]
    assert pytest.approx(tracks[0][5]) == 0.8
    assert tracks[0][6] == 0
    assert tracks[0][7] == 0
    

if __name__ == '__main__':
    sys.exit(pytest.main([__file__]))
