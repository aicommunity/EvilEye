import numpy as np
import datetime
from typing import List
from queue import Empty
from ultralytics.engine.results import Boxes
from ultralytics.trackers.bot_sort import BOTrack
from .object_tracking_base import ObjectTrackingBase
from .trackers.bot_sort import BOTSORT
from .trackers.track_encoder import TrackEncoder
from .trackers.cfg.utils import read_cfg
from ..object_detector.object_detection_base import DetectionResult
from ..object_detector.object_detection_base import DetectionResultList
from .tracking_results import TrackingResult
from .tracking_results import TrackingResultList
from ..core.base_class import EvilEyeBase
from .botsort_config import BostSortCfg


@EvilEyeBase.register("ObjectTrackingBotsort")
class ObjectTrackingBotsort(ObjectTrackingBase):
    #tracker: BOTSORT

    def __init__(self):
        super().__init__()
        self.botsort_cfg = BostSortCfg()
        self.tracker = None
        self.encoders = None
        self.fps = 5

    def init_impl(self, **kwargs):
        try:
            encoders = kwargs.get('encoders', None)
            if encoders is not None:
                onnx_path = self.params.get("tracker_onnx", "models/osnet_ain_x1_0_M.onnx")
                if onnx_path in encoders:
                    encoder = encoders[onnx_path]
                    self.encoders = [encoder]
                    self.logger.debug(f"Using encoder from encoders dict: {onnx_path}")
                else:
                    self.encoders = None
                    self.logger.debug(f"Encoder {onnx_path} not found in encoders dict, ReID disabled")
            else:
                self.encoders = None
                self.logger.debug("No encoders provided, ReID disabled")
            
            super().init_impl(**kwargs)
            # Ensure botsort_cfg is set (should be set by set_params_impl, but check anyway)
            if not self.botsort_cfg:
                # Try to set default config if not set
                self.logger.warning("botsort_cfg not set, using default configuration")
                self.botsort_cfg = BostSortCfg()
            
            self.logger.debug(f"Initializing BOTSORT with fps={self.fps}, with_reid={self.botsort_cfg.with_reid}")
            self.tracker = BOTSORT(self.botsort_cfg, self.encoders, frame_rate=self.fps)
            self.logger.debug("BOTSORT tracker initialized successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize ObjectTrackingBotsort: {e}", exc_info=True)
            self.tracker = None
            return False

    def release_impl(self):
        super().release_impl()
        self.tracker = None

    def reset_impl(self):
        self.tracker.reset()

    def set_params_impl(self):
        self.source_ids = self.params.get('source_ids', [])
        self.fps = self.params.get('fps', 5)
        self.execution_mode = self.params.get('execution_mode', self.execution_mode)

        cfg_dict = self.params.get("botsort_cfg", None)
        if cfg_dict:
            self.botsort_cfg = BostSortCfg(
                appearance_thresh=cfg_dict.get("appearance_thresh", self.botsort_cfg.appearance_thresh),
                gmc_method=cfg_dict.get("gmc_method", self.botsort_cfg.gmc_method),
                match_thresh=cfg_dict.get("match_thresh", self.botsort_cfg.match_thresh),
                new_track_thresh=cfg_dict.get("new_track_thresh", self.botsort_cfg.new_track_thresh),
                proximity_thresh=cfg_dict.get("proximity_thresh", self.botsort_cfg.proximity_thresh),
                track_buffer=cfg_dict.get("track_buffer", self.botsort_cfg.track_buffer),
                track_high_thresh=cfg_dict.get("track_high_thresh", self.botsort_cfg.track_high_thresh),
                track_low_thresh=cfg_dict.get("track_low_thresh", self.botsort_cfg.track_low_thresh),
                tracker_type=cfg_dict.get("tracker_type", self.botsort_cfg.tracker_type),
                fuse_score=cfg_dict.get("fuse_score", self.botsort_cfg.fuse_score),
                with_reid=cfg_dict.get("with_reid", self.botsort_cfg.with_reid),
            )

    def get_params_impl(self):
        params = dict()
        params['source_ids'] = self.source_ids
        params['fps'] = self.fps
        params['botsort_cfg'] = {
            "appearance_thresh": self.botsort_cfg.appearance_thresh,
            "gmc_method": self.botsort_cfg.gmc_method,
            "match_thresh": self.botsort_cfg.match_thresh,
            "new_track_thresh": self.botsort_cfg.new_track_thresh,
            "proximity_thresh": self.botsort_cfg.proximity_thresh,
            "track_buffer": self.botsort_cfg.track_buffer,
            "track_high_thresh": self.botsort_cfg.track_high_thresh,
            "track_low_thresh": self.botsort_cfg.track_low_thresh,
            "tracker_type": self.botsort_cfg.tracker_type,
            "fuse_score": self.botsort_cfg.fuse_score,
            "with_reid": self.botsort_cfg.with_reid,
        }
        return params

    def default(self):
        self.params.clear()

    def _process_impl(self):
        while self.run_flag:
            try:
                detections = self.queue_in.get(timeout=0.5)
            except Empty:
                continue
            if detections is None:
                break
            if self.tracker is None:
                continue
            detection_result, image = detections
            source_id = getattr(detection_result, "source_id", None)
            frame_id = getattr(detection_result, "frame_id", None)
            if isinstance(detection_result, dict):
                source_id = detection_result.get("source_id", source_id)
                frame_id = detection_result.get("frame_id", frame_id)
            
            # Check if image is valid
            if image is None or image.image is None:
                self.logger.warning(
                    f"Received None image for source {source_id if detection_result else 'unknown'}, skipping"
                )
                continue

            # Important contract: emit a result per processed frame (even if empty).
            # Otherwise downstream visualization buffering can stall when there are no detections.
            try:
                if detection_result is None or not getattr(detection_result, "detections", None):
                    if isinstance(detection_result, dict):
                        has_detections = bool(detection_result.get("detections", []))
                    else:
                        has_detections = bool(getattr(detection_result, "detections", None))
                else:
                    has_detections = True
                if not has_detections:
                    tracks_info = TrackingResultList()
                    tracks_info.source_id = source_id
                    tracks_info.frame_id = frame_id
                    tracks_info.time_stamp = datetime.datetime.now()
                    self._put_out_drop_oldest((tracks_info, image))
                    continue
            except Exception:
                # If something is malformed, fall through to normal processing attempt.
                pass
            
            try:
                cam_id, boxes = self._parse_det_info(detection_result, image.image)
                tracks = self.tracker.update(boxes, image.image)
                if len(tracks) > 0:
                    pass
                tracks_info = self._create_tracks_info(cam_id, frame_id, None, tracks)
                # Keep only the freshest tracking results to avoid unbounded memory growth
                self._put_out_drop_oldest((tracks_info, image))
            except Exception as e:
                self.logger.error(
                    f"Error processing detection for source {source_id if detection_result else 'unknown'}: {e}",
                    exc_info=True,
                )
                continue

    def _parse_det_info(self, det_info: DetectionResultList, image: np.ndarray) -> tuple:
        if image is None:
            raise ValueError("image cannot be None")
        
        cam_id = getattr(det_info, "source_id", None)
        objects = getattr(det_info, "detections", None)
        if objects is None and isinstance(det_info, dict):
            cam_id = det_info.get("source_id", cam_id)
            objects = det_info.get("detections", [])
        if objects is None:
            objects = []

        if len(objects) == 0:
            boxes_array = np.empty((0, 6), dtype=np.float32)
            orig_shape = (image.shape[1], image.shape[0])
            return cam_id, Boxes(boxes_array, orig_shape)

        num_objects = len(objects)
        bboxes_xyxy = np.empty((num_objects, 4), dtype=np.float32)
        confidences = np.empty((num_objects, 1), dtype=np.float32)
        class_ids = np.empty((num_objects, 1), dtype=np.float32)

        for i, obj in enumerate(objects):
            if isinstance(obj, dict):
                bbox = obj.get("bounding_box", obj.get("bbox_xyxy", [0, 0, 0, 0]))
                conf = obj.get("confidence", 0.0)
                cls_id = obj.get("class_id", -1)
            else:
                bbox = obj.bounding_box
                conf = obj.confidence
                cls_id = obj.class_id
            bboxes_xyxy[i] = bbox
            confidences[i] = conf
            class_ids[i] = cls_id
        
        boxes_array = np.concatenate([bboxes_xyxy, confidences, class_ids], axis=1)
        
        # Validate image shape
        if not hasattr(image, 'shape') or len(image.shape) < 2:
            raise ValueError(f"Invalid image shape: {image.shape if hasattr(image, 'shape') else 'no shape attribute'}")
        
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

