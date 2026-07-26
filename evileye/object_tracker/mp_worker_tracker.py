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
        from .track_update_core import run_tracker_update

        detection_result, image = self._unpack_input(data)
        if image is None or image.image is None:
            return None
        if self.tracker is None:
            return None
        return run_tracker_update(self.tracker, detection_result, image.image)

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
