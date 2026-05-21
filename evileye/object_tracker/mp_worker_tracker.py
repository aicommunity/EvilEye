from ..core.mp_worker import MpWorker
from ..core.frame_transport import (
    FrameHandle,
    SharedFrameTransport,
    materialize_payload_item,
)
from .botsort_config import botsort_cfg_from_dict


class MpWorkerTracker(MpWorker):
    """Multiprocessing worker that runs BoTSORT tracking in a child process

    The ONNX encoder and BOTSORT tracker are initialized inside the
    child process because they cannot be pickled across process
    boundaries
    """

    def __init__(self, input_queue, output_queue, log_queue=None, stop_event=None):
        super().__init__(input_queue, output_queue, log_queue=log_queue, stop_event=stop_event)
        self.tracker_params = {}
        self.tracker = None
        self.encoders = None
        self._frame_transport = SharedFrameTransport()

    def set_params(self, tracker_params: dict):
        """Store params to be used during init_worker inside child process"""
        self.tracker_params = tracker_params

    def get_spawn_state(self):
        return {"tracker_params": dict(self.tracker_params or {})}

    def apply_spawn_state(self, state):
        self.set_params(state.get("tracker_params", {}))

    def init_worker(self):
        """Initialize BOTSORT tracker inside the child process"""
        from .trackers.bot_sort import BOTSORT

        cfg = botsort_cfg_from_dict(self.tracker_params.get("botsort_cfg", {}))

        # Initialize ONNX encoder inside child process
        onnx_path = self.tracker_params.get("tracker_onnx", "")
        if onnx_path and cfg.with_reid:
            try:
                from .trackers.onnx_encoder import OnnxEncoder
                self.encoders = [OnnxEncoder(onnx_path)]
            except Exception:
                self.encoders = None
        else:
            self.encoders = None

        fps = self.tracker_params.get('fps', 5)
        self.tracker = BOTSORT(cfg, self.encoders, frame_rate=fps)

    def worker_impl(self, data):
        """Process one (detection_result, image) pair and return tracking results

        Data arrives as a tuple (detection_result, image) serialized via
        pickle.  We run the tracker update and return (tracking_result_list, image)
        """
        import numpy as np
        import datetime
        from ultralytics.engine.results import Boxes
        from .tracking_results import TrackingResult, TrackingResultList

        detection_result, image = self._unpack_input(data)
        if image is None or image.image is None:
            return None

        cam_id = detection_result.source_id
        objects = detection_result.detections

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
        boxes_array = np.concatenate([bboxes_xyxy, confidences, class_ids], axis=1)
        orig_shape = (image.image.shape[1], image.image.shape[0])
        boxes = Boxes(boxes_array, orig_shape)

        tracks = self.tracker.update(boxes, image.image)

        tracks_info = TrackingResultList()
        tracks_info.source_id = cam_id
        tracks_info.frame_id = detection_result.frame_id
        tracks_info.time_stamp = datetime.datetime.now()

        if len(tracks) > 0:
            tracks_results = np.asarray([x.result for x in tracks], dtype=np.float32)
            for i in range(len(tracks_results)):
                obj = TrackingResult()
                obj.class_id = int(tracks_results[i, 6])
                obj.bounding_box = tracks_results[i, :4].tolist()
                obj.confidence = float(tracks_results[i, 5])
                obj.track_id = int(tracks_results[i, 4])
                obj.tracking_data = {"track_object": tracks[i]}
                tracks_info.tracks.append(obj)

        return tracks_info

    def _unpack_input(self, data):
        """Unpack either legacy tuple payload or descriptor payload."""
        if isinstance(data, dict) and "detection_result" in data:
            det = data.get("detection_result")
            handle = data.get("frame_handle")
            if isinstance(handle, FrameHandle):
                image_np = materialize_payload_item(handle, self._frame_transport)
            else:
                image_np = None
            frame_meta = data.get("frame_meta", {}) or {}

            class _FrameLike:
                pass

            frame = _FrameLike()
            frame.image = image_np
            frame.source_id = frame_meta.get("source_id")
            frame.frame_id = frame_meta.get("frame_id")
            frame.time_stamp = frame_meta.get("time_stamp")
            frame.current_video_frame = frame_meta.get("current_video_frame")
            frame.current_video_position = frame_meta.get("current_video_position")
            frame.source_video_duration = frame_meta.get("source_video_duration")
            return det, frame
        if isinstance(data, (list, tuple)) and len(data) >= 2:
            return data[0], data[1]
        return None, None

    def cleanup(self):
        self.tracker = None
        self.encoders = None
