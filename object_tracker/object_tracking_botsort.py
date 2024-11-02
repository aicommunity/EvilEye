import numpy as np
import datetime
from object_tracker import object_tracking_base
from object_tracker.trackers.bot_sort import BOTSORT
from object_tracker.trackers.cfg.utils import read_cfg
from time import sleep
from object_detector.object_detection_base import DetectionResult
from object_detector.object_detection_base import DetectionResultList
from object_tracker.object_tracking_base import TrackingResult
from object_tracker.object_tracking_base import TrackingResultList


class ObjectTrackingBotsort(object_tracking_base.ObjectTrackingBase):
    tracker: BOTSORT

    def __init__(self):
        super().__init__()

    def init_impl(self):
        # TODO: add mechanism of setting cfg and replace this in the future
        cfg = read_cfg()
        self.tracker = BOTSORT(args=cfg, frame_rate=30)
        return True

    def release_impl(self):
        self.tracker = None

    def reset_impl(self):
        self.tracker.reset()

    def set_params_impl(self):
        self.source_ids = self.params.get('source_ids', [])
        pass  # TODO: add applying params to tracker instance

    def default(self):
        self.params.clear()

    def _process_impl(self):
        while self.run_flag:
            sleep(0.01)
            detections = self.queue_in.get()
            if detections is None:
                break
            detection_result, image = detections
            cam_id, bboxes_xcycwh, confidences, class_ids = self._parse_det_info(detection_result)
            tracks = self.tracker.update(class_ids, bboxes_xcycwh, confidences)
            tracks_info = self._create_tracks_info(cam_id, detection_result.frame_id, None, tracks)
            self.queue_out.put((tracks_info, image))

    def _parse_det_info(self, det_info: DetectionResultList) -> tuple:
        cam_id = det_info.source_id
        objects = det_info.detections

        bboxes_xyxy = []
        confidences = []
        class_ids = []

        for obj in objects:
            bboxes_xyxy.append(obj.bounding_box)
            confidences.append(obj.confidence)
            class_ids.append(obj.class_id)

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

    def _create_tracks_info(self, cam_id: int, frame_id: int, detection: DetectionResult, tracks: np.ndarray):
        tracks_info = TrackingResultList()
        tracks_info.source_id = cam_id
        tracks_info.frame_id = frame_id
        tracks_info.time_stamp = datetime.datetime.now()

        # print(tracks)
        for i in range(len(tracks)):
            track_bbox = tracks[i, :4].tolist()
            track_conf = tracks[i, 5]
            track_cls = int(tracks[i, 6])
            track_id = int(tracks[i, 4])
            object_info = TrackingResult()
            object_info.class_id = track_cls
            object_info.bounding_box = track_bbox
            object_info.confidence = float(track_conf)
            object_info.track_id = track_id
            if detection:
                object_info.detection_history.append(detection)

            tracks_info.tracks.append(object_info)

        return tracks_info

