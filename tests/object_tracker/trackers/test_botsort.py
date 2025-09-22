import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger
import sys
import pytest
import numpy as np
from pathlib import Path
from types import SimpleNamespace

sys.path.append(str(Path(__file__).parent.parent.parent.parent))
from object_tracker.trackers.cfg.utils import read_cfg
from object_tracker.trackers.bot_sort import BOTSORT


# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_botsort():
    cfg = read_cfg()
    tracker = BOTSORT(args=cfg, frame_rate=30)
    
    cls = np.array([0])
    xywh = np.array([[0.5, 0.5, 1., 1.]])
    conf = np.array([0.8])
    
    tracks = tracker.update(cls, xywh, conf, None)
    test_logger.info(tracks)
    assert tracks.shape == (1, 8)
    assert tracks[0][0:4].tolist() == [0, 0, 1, 1]
    assert pytest.approx(tracks[0][5]) == 0.8
    assert tracks[0][6] == 0
    assert tracks[0][7] == 0
    

if __name__ == '__main__':
    sys.exit(pytest.main([__file__]))
