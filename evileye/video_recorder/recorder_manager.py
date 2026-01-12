from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional, Dict, Any

from evileye.core.logger import get_module_logger
from evileye.video_recorder.recording_params import RecordingParams
from evileye.video_recorder.recorder_base import VideoRecorderBase, SourceMeta


class RecorderManager:
    """Lifecycle and backend selection for video recording.

    Chooses GStreamer recorder when capture backend is GStreamer and OpenCV
    recorder otherwise. Provides simple start/stop API and owns current recorder.
    """

    def __init__(self) -> None:
        self.logger = get_module_logger("recorder_manager")
        self.params: RecordingParams = RecordingParams()
        self.recorder: Optional[VideoRecorderBase] = None
        self.rotation_lock = threading.Lock()

    def configure(self, params: RecordingParams) -> None:
        self.params = params

    def create_recorder(self, backend: str, source_meta: SourceMeta) -> VideoRecorderBase:
        # Prefer ffmpeg for VideoFile copy without GLib/Qt conflicts
        if backend.lower().startswith("gstreamer"):
            if source_meta.source_type and str(source_meta.source_type).lower() in ("videofile", "video_file", "file"):
                from .recorder_ffmpeg import FfmpegRecorder
                return FfmpegRecorder()
            from .recorder_gstreamer import GStreamerRecorder
            return GStreamerRecorder()
        else:
            from .recorder_opencv import OpenCVRecorder
            return OpenCVRecorder()

    def start(self, backend: str, source_meta: SourceMeta, params: Optional[RecordingParams] = None) -> None:
        if params is None:
            params = self.params
        if not params.enabled:
            self.logger.info("Recording disabled; manager start skipped")
            return
        self.recorder = self.create_recorder(backend, source_meta)
        self.logger.info(f"Starting recorder backend={backend} container={params.container} out_dir={params.out_dir}")
        self.recorder.start(source_meta, params)

    def rotate(self) -> None:
        if self.recorder:
            with self.rotation_lock:
                self.recorder.rotate_segment()

    def stop(self) -> None:
        if self.recorder:
            self.recorder.stop()
            self.recorder = None


