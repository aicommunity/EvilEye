import numpy as np
import datetime
from typing import List
from ultralytics.engine.results import Boxes
from ultralytics.trackers.bot_sort import BOTrack
from .object_tracking_base import ObjectTrackingBase
from .trackers.bot_sort import BOTSORT
from .trackers.track_encoder import TrackEncoder
from .trackers.cfg.utils import read_cfg
from time import sleep
from ..object_detector.object_detection_base import DetectionResult
from ..object_detector.object_detection_base import DetectionResultList
from .tracking_results import TrackingResult
from .tracking_results import TrackingResultList
from dataclasses import dataclass
import copy
from ..core.base_class import EvilEyeBase

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
    fuse_score: bool = True
    with_reid: bool = False



@EvilEyeBase.register("ObjectTrackingBotsort")
class ObjectTrackingBotsort(ObjectTrackingBase):
    #tracker: BOTSORT

    def __init__(self):
        super().__init__()
        self.botsort_cfg = BostSortCfg()
        self.tracker = None
        self.encoders = None
        self.fps = 5

        self.cfg_dict = dict()
        self.cfg_dict["appearance_thresh"] = 0.25
        self.cfg_dict["gmc_method"] = "sparseOptFlow"
        self.cfg_dict["match_thresh"] = 0.8
        self.cfg_dict["new_track_thresh"] = 0.6
        self.cfg_dict["proximity_thresh"] = 0.5
        self.cfg_dict["track_buffer"] = 30
        self.cfg_dict["track_high_thresh"] = 0.5
        self.cfg_dict["track_low_thresh"] = 0.1
        self.cfg_dict["tracker_type"] = "botsort"
        self.cfg_dict["with_reid"] = False

    def init_impl(self, **kwargs):
        encoders = kwargs.get('encoders', None)
        if encoders is not None:
            onnx_path = self.params.get("tracker_onnx", "models/osnet_ain_x1_0_M.onnx")
            if onnx_path in encoders:
                encoder = encoders[onnx_path]
                self.encoders = [encoder]
            else:
                self.encoders = None
        super().init_impl(**kwargs)
        if not self.botsort_cfg:
            self.tracker = None
            return False

        self.tracker = BOTSORT(self.botsort_cfg, self.encoders, frame_rate=self.fps)

    def release_impl(self):
        super().init_impl()
        self.tracker = None

    def reset_impl(self):
        self.tracker.reset()

    def set_params_impl(self):
        self.source_ids = self.params.get('source_ids', [])
        self.fps = self.params.get('fps', 5)

        self.cfg_dict = self.params.get('botsort_cfg', self.cfg_dict)
        cfg_dict = self.cfg_dict

        if cfg_dict:
            self.botsort_cfg = BostSortCfg(appearance_thresh=cfg_dict["appearance_thresh"], gmc_method=cfg_dict["gmc_method"],
                                           match_thresh=cfg_dict["match_thresh"], new_track_thresh=cfg_dict["new_track_thresh"],
                                           proximity_thresh=cfg_dict["proximity_thresh"], track_buffer=cfg_dict["track_buffer"],
                                           track_high_thresh=cfg_dict["track_high_thresh"], track_low_thresh=cfg_dict["track_low_thresh"],
                                           tracker_type=cfg_dict["tracker_type"], with_reid=cfg_dict["with_reid"])

    def get_params_impl(self):
        params = dict()
        params['source_ids'] = self.source_ids
        params['fps'] = self.fps
        params['botsort_cfg'] = self.cfg_dict
        return params

    def default(self):
        self.params.clear()

    def _process_impl(self):
        while self.run_flag:
            sleep(0.01)
            detections = self.queue_in.get()
            if detections is None:
                continue
            if self.tracker is None:
                continue
            detection_result, image = detections
            cam_id, boxes = self._parse_det_info(detection_result, image.image)
            tracks = self.tracker.update(boxes, image.image)
            if len(tracks) > 0:
                pass
            tracks_info = self._create_tracks_info(cam_id, detection_result.frame_id, None, tracks)
            self.queue_out.put((tracks_info, image))

    def _parse_det_info(self, det_info: DetectionResultList, image: np.ndarray) -> tuple:
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
        confidences = np.array(confidences).reshape(-1, 1)
        class_ids = np.array(class_ids).reshape(-1, 1)

        bboxes_xyxy = np.array(bboxes_xyxy)
        confidences = np.array(confidences)
        class_ids = np.array(class_ids)
        
        boxes_array = np.concatenate([bboxes_xyxy, confidences, class_ids], axis=1)
        orig_shape = (image.shape[1], image.shape[0])
        boxes = Boxes(boxes_array, orig_shape)
        return cam_id, boxes

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

