import numpy as np
import datetime
from object_tracker import object_tracking_base
from object_tracker.trackers.bot_sort import BOTSORT, Encoder, BOTrack
from object_tracker.trackers.cfg.utils import read_cfg
from time import sleep
from object_detector.object_detection_base import DetectionResult
from object_detector.object_detection_base import DetectionResultList
from object_tracker.object_tracking_base import TrackingResult
from object_tracker.object_tracking_base import TrackingResultList
from dataclasses import dataclass
import copy

@dataclass
class BostSortCfg:
    appearance_thresh: float = 0.25
    gmc_method: str = "sparseOptFlow"
    match_thresh: float = 0.8
    new_track_thresh: float = 0.6
    proximity_thresh: float = 0.5
    track_buffer: int = 30
    track_high_thresh: float = 0.5
    track_low_thresh: float = 0.1
    tracker_type: str = "botsort"
    with_reid: bool = False


class ObjectTrackingBotsort(object_tracking_base.ObjectTrackingBase):
    #tracker: BOTSORT

    def __init__(self, encoder: Encoder = None):
        super().__init__()
        self.botsort_cfg = BostSortCfg()
        self.tracker = None
        self.encoder = encoder
        self.fps = 5

    def init_impl(self):
        if not self.botsort_cfg:
            print(f"BOTSORT parameters not found!")
            self.tracker = None
            return False

        self.tracker = BOTSORT(self.botsort_cfg, self.encoder, frame_rate=self.fps)
        return True

    def release_impl(self):
        self.tracker = None

    def reset_impl(self):
        self.tracker.reset()

    def set_params_impl(self):
        self.source_ids = self.params.get('source_ids', [])
        self.fps = self.params.get('fps', 5)

        cfg_dict = self.params.get('botsort_cfg', None)

        if cfg_dict:
            self.botsort_cfg = BostSortCfg(appearance_thresh=cfg_dict["appearance_thresh"], gmc_method=cfg_dict["gmc_method"],
                                           match_thresh=cfg_dict["match_thresh"], new_track_thresh=cfg_dict["new_track_thresh"],
                                           proximity_thresh=cfg_dict["proximity_thresh"], track_buffer=cfg_dict["track_buffer"],
                                           track_high_thresh=cfg_dict["track_high_thresh"], track_low_thresh=cfg_dict["track_low_thresh"],
                                           tracker_type=cfg_dict["tracker_type"], with_reid=cfg_dict["with_reid"])

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
            tracks = copy.deepcopy(self.tracker.update(class_ids, bboxes_xcycwh, confidences, image.image))
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

    def _create_tracks_info(
            self, 
            cam_id: int, 
            frame_id: int, 
            detection: DetectionResult, 
            tracks: list[BOTrack]):
        
        tracks_info = TrackingResultList()
        tracks_info.source_id = cam_id
        tracks_info.frame_id = frame_id
        tracks_info.time_stamp = datetime.datetime.now()

        # print(tracks)
        tracks_results = np.asarray([x.result for x in tracks], dtype=np.float32)
        for i in range(len(tracks_results)):
            track_bbox = tracks_results[i, :4].tolist()
            track_conf = tracks_results[i, 5]
            track_cls = int(tracks_results[i, 6])
            track_id = int(tracks_results[i, 4])
            object_info = TrackingResult()
            object_info.class_id = track_cls
            object_info.bounding_box = track_bbox
            object_info.confidence = float(track_conf)
            object_info.track_id = track_id
            if detection:
                object_info.detection_history.append(detection)
            
            # Add BOTrack object to tracking data
            # in order to use it in multi-camera tracking during reidentification
            object_info.tracking_data = {
                "track_object": tracks[i],
            }

            tracks_info.tracks.append(object_info)

        return tracks_info

