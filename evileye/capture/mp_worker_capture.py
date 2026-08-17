"""Multiprocessing worker for video capture.

Runs GStreamer or OpenCV capture in a child process and continuously
pushes CaptureImage objects into the output queue.  Unlike other
MpWorker subclasses that use request-response, this worker is a
**continuous producer**: it overrides ``__call__`` to loop
autonomously until stopped.
"""
from __future__ import annotations

import sys
import time
from queue import Empty, Full

from ..core.mp_worker import MpWorker
from ..core.processor_base import EXEC_MODE_THREAD
from ..core.frame_transport import SharedFrameTransport

# Exit code listed in capture MpControl no_restart_exit_codes — stops restart storms.
CAPTURE_INIT_FAIL_EXIT_CODE = 2


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
        self._last_full_ipc_ts = 0.0

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

    def _log_recording_status(self, capture) -> None:
        try:
            rp = getattr(capture, "recording_params", None)
            rm = getattr(capture, "recorder_manager", None)
            gst_rec = getattr(capture, "_gst_continuous_recorder", None)
            if rp is None:
                self.logger.warning(
                    "Capture worker started without recording_params for %s",
                    self._capture_params.get("camera", "?"),
                )
                return
            continuous = bool(rp.enabled and rp.continuous_recording_enabled)
            opencv_active = bool(rm and getattr(rm, "recorder", None))
            gst_active = bool(
                gst_rec is not None
                and (
                    getattr(gst_rec, "is_running", False)
                    or getattr(gst_rec, "_refs", None) is not None
                )
            )
            # GStreamer continuous recording is tee-integrated; OpenCV uses recorder_manager.
            recorder_active = opencv_active or gst_active
            backend = "gstreamer" if gst_active else ("opencv" if opencv_active else "none")
            self.logger.info(
                "Capture worker recording: source=%s enabled=%s continuous=%s "
                "recorder_active=%s backend=%s out_dir=%s",
                self._capture_params.get("source_names"),
                rp.enabled,
                rp.continuous_recording_enabled,
                recorder_active,
                backend,
                rp.out_dir,
            )
            if continuous and not recorder_active:
                self.logger.error(
                    "Continuous recording is enabled but recorder did not start for %s",
                    self._capture_params.get("source_names"),
                )
        except Exception as exc:
            self.logger.debug("Could not log capture recording status: %s", exc)

    def _init_capture_instance(self, capture, params: dict) -> bool:
        capture.set_params(**params)
        if not capture.init():
            return False

        capture.start()
        self._log_recording_status(capture)
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
        from evileye.core.gstreamer_runtime import ensure_gstreamer_spawn_runtime

        ensure_gstreamer_spawn_runtime()
        params = self._capture_params

        capture_type = params.get("type", "")

        use_gstreamer = (
                "gstreamer" in capture_type.lower()
                or params.get("backend") == "gstreamer"
        )

        child_params = dict(params)
        # Capture already runs in a child process; backend must use in-process threads.
        child_params["execution_mode"] = EXEC_MODE_THREAD
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
            sys.exit(CAPTURE_INIT_FAIL_EXIT_CODE)

        if self._capture is None:
            self.logger.error("Capture object is None after init — exiting")
            sys.exit(CAPTURE_INIT_FAIL_EXIT_CODE)

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

            from .queue_policy import put_drop_oldest

            for frame in frames:
                packed = self._pack_frame_for_ipc(frame)
                handle = (
                    packed.get("frame_handle")
                    if isinstance(packed, dict)
                    else None
                )
                ok = put_drop_oldest(
                    self.output_queue,
                    packed,
                    on_drop=self._release_packed_frame,
                )
                if ok and handle is not None:
                    self._frame_transport.relinquish_frame(handle)
                elif not ok:
                    self._release_packed_frame(packed)

            self._maybe_push_full_frame()

        try:
            self.cleanup()
        except Exception:
            pass
        self.logger.info("Capture worker exiting")

    def _maybe_push_full_frame(self) -> None:
        """Send throttled uncropped frame to parent for split-editor preview."""
        cap = self._capture
        if cap is None or not getattr(cap, "split_stream", False):
            return
        full = getattr(cap, "_latest_full_frame", None)
        ts = float(getattr(cap, "_latest_full_frame_ts", 0.0) or 0.0)
        if full is None or ts <= 0.0:
            return
        if ts <= float(self._last_full_ipc_ts or 0.0):
            return
        ids = [int(x) for x in (getattr(cap, "source_ids", None) or []) if x is not None]
        primary = ids[0] if ids else None
        try:
            handle = self._frame_transport.alloc_frame(
                full, frame_id=0, timestamp=ts
            )
        except Exception:
            return
        packed = {
            "frame_handle": handle,
            "frame_meta": {
                "kind": "full_frame",
                "source_id": primary,
                "primary_source_id": primary,
                "source_ids": ids,
                "time_stamp": ts,
                "frame_id": None,
            },
        }
        from .queue_policy import put_drop_oldest

        ok = put_drop_oldest(
            self.output_queue,
            packed,
            on_drop=self._release_packed_frame,
        )
        if ok:
            self._last_full_ipc_ts = ts
            try:
                self._frame_transport.relinquish_frame(handle)
            except Exception:
                pass
        else:
            self._release_packed_frame(packed)

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
                "pts_ns": getattr(frame, "pts_ns", None),
                "media_pts_sec": getattr(frame, "media_pts_sec", None),
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
        try:
            self._frame_transport.release_all()
        except Exception:
            pass
