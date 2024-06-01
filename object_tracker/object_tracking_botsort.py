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
        pass  # TODO: add applying params to tracker instance

    def default(self):
        self.params.clear()

    def process_impl(
            self,
            det_info: dict,
            is_actual: bool = True,
            img: np.ndarray = None) -> tuple:

        # TODO: add implementation for `is_actual` (ignoring frames)
        cam_id, bboxes_xcycwh, confidences, class_ids = self._parse_det_info(det_info)

        # Update tracker with new detections and get current tracks
        tracks = self.tracker.update(class_ids, bboxes_xcycwh, confidences, img)

        tracks_info = self._create_tracks_info(cam_id, tracks)
        return tracks_info

    def _parse_det_info(self, det_info: dict) -> tuple:
        cam_id = det_info['cam_id']
        objects = det_info['objects']

        bboxes_xyxy = []
        confidences = []
        class_ids = []

        for obj in objects:
            bboxes_xyxy.append(obj['bbox'])
            confidences.append(obj['conf'])
            class_ids.append(obj['class'])

        bboxes_xyxy = np.array(bboxes_xyxy).reshape(-1, 4)
        confidences = np.array(confidences)
        class_ids = np.array(class_ids)

        bboxes_xyxy = np.array(bboxes_xyxy)
        confidences = np.array(confidences)
        class_ids = np.array(class_ids)

        # Convert XYXY input coordinates to XcYcWH
        bboxes_xcycwh = bboxes_xyxy.astype('float64')
        bboxes_xcycwh[:, 2] -= bboxes_xcycwh[:, 0]
        bboxes_xcycwh[:, 3] -= bboxes_xcycwh[:, 1]
        bboxes_xcycwh[:, 0] += bboxes_xcycwh[:, 2] / 2
        bboxes_xcycwh[:, 1] += bboxes_xcycwh[:, 3] / 2

        return cam_id, bboxes_xcycwh, confidences, class_ids

    def _create_tracks_info(self, cam_id: int, tracks: np.ndarray):
        tracks_info = {'cam_id': cam_id, 'objects': [], 'module_name': 'tracking'}
        # print(tracks)
        for i in range(len(tracks)):
            track_bbox = tracks[i, :4].tolist()
            track_conf = tracks[i, 5]
            track_cls = tracks[i, 6]
            track_id = tracks[i, 4]
            object_info = {
                'bbox': track_bbox,
                'conf': track_conf,
                'class': track_cls,
                'track_id': track_id,
            }
            tracks_info['objects'].append(object_info)

        return tracks_info