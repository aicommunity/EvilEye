import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger
import sys
import pytest
import numpy as np
from pathlib import Path
from types import SimpleNamespace

sys.path.append(str(Path(__file__).parent.parent.parent.parent))
from evileye.object_tracker.trackers.cfg.utils import read_cfg
from evileye.object_tracker.trackers.bot_sort import BOTSORT


# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_botsort():
    cfg = read_cfg()
    # Ensure cfg has all required attributes
    if not hasattr(cfg, 'fuse_score'):
        cfg.fuse_score = True
    if not hasattr(cfg, 'track_high_thresh'):
        cfg.track_high_thresh = 0.5
    if not hasattr(cfg, 'track_low_thresh'):
        cfg.track_low_thresh = 0.1
    if not hasattr(cfg, 'match_thresh'):
        cfg.match_thresh = 0.8
    
    tracker = BOTSORT(args=cfg, frame_rate=30)
    
    # Create a mock Boxes object for BOTSORT.update()
    from types import SimpleNamespace
    
    # Create mock results object
    cls = np.array([0])
    xywh = np.array([[0.5, 0.5, 1., 1.]])
    conf = np.array([0.8])
    
    # Create a simple mock Boxes object that matches what BOTSORT.update() expects
    mock_boxes = SimpleNamespace()
    mock_boxes.conf = conf
    mock_boxes.xywh = xywh
    mock_boxes.cls = cls
    # Add xywhr if needed
    if not hasattr(mock_boxes, 'xywhr'):
        mock_boxes.xywhr = xywh
    
    tracks = tracker.update(mock_boxes, img=None)
    test_logger.info(f"Tracks: {tracks}, type: {type(tracks)}")
    # BOTSORT.update() returns List[SCTrack]
    assert isinstance(tracks, list)
    if len(tracks) > 0:
        # Check first track
        track = tracks[0]
        assert hasattr(track, 'tlbr') or hasattr(track, 'tlwh') or hasattr(track, 'xywh')
