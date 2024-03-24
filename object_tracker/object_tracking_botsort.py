import cv2
import numpy as np
from utils import utils
from object_tracker import object_tracking_base
from object_tracker.trackers.bot_sort import BOTSORT
from object_tracker.trackers.cfg.utils import read_cfg


class ObjectTrackingBotsort(object_tracking_base.ObjectTrackingBase):
    tracker: BOTSORT
    
    def __init__(self):
        super().__init__()
        self.init_impl()
        self.is_inited = True

    def init_impl(self):
        # TODO: add mechanism of setting cfg and replace this in the future
        cfg = read_cfg()

        self.tracker = BOTSORT(args=cfg, frame_rate=30)
        return True

    def reset_impl(self):
        self.tracker.reset()

    def set_params_impl(self, params: dict):
        pass # TODO: add applying params to tracker instance

    def default(self):
        self.params.clear()

    def process_impl(
            self, 
            bboxes_coords: np.ndarray, 
            confidences: np.ndarray, 
            class_ids: np.ndarray, 
            is_actual: bool = True, 
            img: np.ndarray = None) -> tuple:
        
        # TODO: add implementation for `is_actual` (ignoring frames)

        # Convert XYXY input coordinates to XcYcWH
        bboxes_xcycwh = bboxes_coords.astype('float64')
        bboxes_xcycwh[:, 2] -= bboxes_xcycwh[:, 0]
        bboxes_xcycwh[:, 3] -= bboxes_xcycwh[:, 1]
        bboxes_xcycwh[:, 0] += bboxes_xcycwh[:, 2] / 2
        bboxes_xcycwh[:, 1] += bboxes_xcycwh[:, 3] / 2

        # Update tracker with new detections and get current tracks
        tracks = self.tracker.update(class_ids, bboxes_xcycwh, confidences, img)
        
        track_bboxes = tracks[:, :4]
        track_conf = tracks[:, 5]
        track_cls = tracks[:, 6]
        track_ids = tracks[:, 7]

        return track_bboxes, track_conf, track_cls, track_ids 
