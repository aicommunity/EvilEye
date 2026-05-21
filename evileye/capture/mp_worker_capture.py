"""Multiprocessing worker for video capture.

Runs GStreamer or OpenCV capture in a child process and continuously
pushes CaptureImage objects into the output queue.  Unlike other
MpWorker subclasses that use request-response, this worker is a
**continuous producer**: it overrides ``__call__`` to loop
autonomously until stopped.
"""
from __future__ import annotations

import time
from queue import Empty, Full

from ..core.mp_worker import MpWorker
from ..core.frame_transport import SharedFrameTransport


class MpWorkerCapture(MpWorker):
    """Capture worker that runs in a child process.

    Lifecycle
    ---------
    1. Parent calls ``set_params(params)`` before ``MpControl.start()``.
    2. ``init_worker()`` creates the capture backend inside the child.
    3. ``__call__`` runs the capture loop until poison pill / stop event.
    4. ``cleanup()`` tears down capture resources.
    """

    def __init__(self, input_queue, output_queue, log_queue=None, stop_event=None):
        super().__init__(input_queue, output_queue, log_queue=log_queue, stop_event=stop_event)
        self._capture_params: dict = {}
        self._capture = None
        self._frame_transport = SharedFrameTransport()

    def set_params(self, params: dict) -> None:
        self._capture_params = dict(params) if params else {}

    def get_spawn_state(self):
        return {"capture_params": dict(self._capture_params)}

    def apply_spawn_state(self, state):
        self.set_params(state.get("capture_params", {}))

    def _create_capture(self, use_gstreamer: bool):
        if use_gstreamer:
            from .video_capture_gstreamer import VideoCaptureGStreamer
            return VideoCaptureGStreamer()

        from .video_capture_opencv import VideoCaptureOpencv
        return VideoCaptureOpencv()

    def _init_capture_instance(self, capture, params: dict) -> bool:
        capture.set_params(**params)
        if not capture.init():
            return False

        capture.start()
        self._capture = capture
        self.logger.info(
            "Capture worker initialised: type=%s source=%s",
            capture.__class__.__name__,
            params.get("camera", "?"),
        )
        return True

    # -- MpWorker interface ----------------------------------------------

    def init_worker(self) -> None:
        """Create and initialise the capture backend inside child process."""
        params = self._capture_params

        capture_type = params.get("type", "")

        use_gstreamer = (
            "gstreamer" in capture_type.lower()
            or params.get("backend") == "gstreamer"
        )

        child_params = dict(params)
        child_params.pop("execution_mode", None)
        capture = self._create_capture(use_gstreamer=use_gstreamer)

        if self._init_capture_instance(capture, child_params):
            return

        if use_gstreamer and not getattr(capture, "gstreamer_available", True):
            self.logger.warning(
                "GStreamer runtime is unavailable in worker process; "
                "falling back to VideoCaptureOpencv for source=%s",
                child_params.get("camera", "?"),
            )
            child_params["type"] = "VideoCaptureOpencv"
            fallback_capture = self._create_capture(use_gstreamer=False)
            if self._init_capture_instance(fallback_capture, child_params):
                return

        self.logger.error("Capture init failed in worker")

    def worker_impl(self, data):
        """Not used — continuous loop in __call__ replaces request-response."""
        return data

    def __call__(self) -> None:
        """Main entry point executed in the child process."""
        self._init_logger()
        try:
            self.init_worker()
        except Exception as e:
            self.logger.error("Capture worker init failed: %s", e, exc_info=True)
            return

        if self._capture is None:
            self.logger.error("Capture object is None after init — exiting")
            return

        self.logger.info("Capture worker ready, entering frame loop")

        while not self._stop_event.is_set():
            try:
                cmd = self.input_queue.get_nowait()
                if cmd is None:
                    break
            except Empty:
                pass

            try:
                frames = self._capture.get()
            except Exception as e:
                self.logger.error("Capture get() error: %s", e)
                time.sleep(0.05)
                continue

            if not frames:
                if self._capture.is_finished():
                    self.logger.info("Source finished (EOF) — exiting worker")
                    break
                time.sleep(0.002)
                continue

            for frame in frames:
                packed = self._pack_frame_for_ipc(frame)
                handle = (
                    packed.get("frame_handle")
                    if isinstance(packed, dict)
                    else None
                )
                try:
                    self.output_queue.put(packed, timeout=0.5)
                    if handle is not None:
                        self._frame_transport.relinquish_frame(handle)
                except Full:
                    try:
                        dropped = self.output_queue.get_nowait()
                        self._release_packed_frame(dropped)
                    except Empty:
                        pass
                    try:
                        self.output_queue.put_nowait(packed)
                        if handle is not None:
                            self._frame_transport.relinquish_frame(handle)
                    except Full:
                        self._release_packed_frame(packed)
                        pass

        try:
            self.cleanup()
        except Exception:
            pass
        self.logger.info("Capture worker exiting")

    def _pack_frame_for_ipc(self, frame):
        image = getattr(frame, "image", None)
        if image is None:
            return frame
        frame_id = int(getattr(frame, "frame_id", 0) or 0)
        timestamp = float(getattr(frame, "time_stamp", time.time()) or time.time())
        handle = self._frame_transport.alloc_frame(
            image, frame_id=frame_id, timestamp=timestamp
        )
        return {
            "frame_handle": handle,
            "frame_meta": {
                "source_id": getattr(frame, "source_id", None),
                "frame_id": getattr(frame, "frame_id", None),
                "current_video_frame": getattr(frame, "current_video_frame", None),
                "current_video_position": getattr(frame, "current_video_position", None),
                "source_video_duration": getattr(frame, "source_video_duration", None),
                "time_stamp": getattr(frame, "time_stamp", None),
            },
        }

    def _release_packed_frame(self, packed):
        try:
            if not isinstance(packed, dict):
                return
            handle = packed.get("frame_handle")
            if handle is None:
                return
            self._frame_transport.release_frame(handle)
        except Exception:
            pass

    def cleanup(self) -> None:
        try:
            self._frame_transport.release_all_owned()
        except Exception:
            pass
        if self._capture is not None:
            try:
                self._capture.stop()
            except Exception:
                pass
            try:
                self._capture.release()
            except Exception:
                pass
            self._capture = None
