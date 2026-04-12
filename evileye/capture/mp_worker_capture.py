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


class MpWorkerCapture(MpWorker):
    """Capture worker that runs in a child process.

    Lifecycle
    ---------
    1. Parent calls ``set_params(params)`` before ``MpControl.start()``.
    2. ``init_worker()`` creates the capture backend inside the child.
    3. ``__call__`` runs the capture loop until poison pill / stop event.
    4. ``cleanup()`` tears down capture resources.
    """

    def __init__(self, input_queue, output_queue, log_queue=None):
        super().__init__(input_queue, output_queue, log_queue=log_queue)
        self._capture_params: dict = {}
        self._capture = None

    def set_params(self, params: dict) -> None:
        self._capture_params = dict(params) if params else {}

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
                try:
                    self.output_queue.put(frame, timeout=0.5)
                except Full:
                    try:
                        self.output_queue.get_nowait()
                    except Empty:
                        pass
                    try:
                        self.output_queue.put_nowait(frame)
                    except Full:
                        pass

        try:
            self.cleanup()
        except Exception:
            pass
        self.logger.info("Capture worker exiting")

    def cleanup(self) -> None:
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
