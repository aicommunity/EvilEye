from __future__ import annotations

from typing import Optional

from evileye.video_recorder.recording_params import RecordingParams
from evileye.video_recorder.recorder_base import SourceMeta, VideoRecorderBase
from evileye.video_recorder.continuous_recorder_opencv import OpenCVContinuousRecorder


class ContinuousRecorderManager:
    """
    Обёртка над конкретным continuous-рекордером.

    Для OpenCV-источников использует OpenCVContinuousRecorder.
    Для GStreamer-источников позже будет использовать GstContinuousRecorder.
    """

    def __init__(self, params: RecordingParams) -> None:
        self.params = params
        self.recorder: Optional[VideoRecorderBase] = None

    def configure(self, params: RecordingParams) -> None:
        self.params = params

    def init_for_opencv(self, source_meta: SourceMeta) -> None:
        if not (self.params.enabled and self.params.continuous_recording_enabled):
            self.recorder = None
            return
        rec = OpenCVContinuousRecorder()
        rec.start(source_meta, self.params)
        self.recorder = rec

    def start(self, backend: str, source_meta: SourceMeta, params: Optional[RecordingParams] = None) -> None:
        # Keep signature compatible with RecorderManager used in VideoCaptureBase.
        if params is not None:
            self.params = params
        if not (self.params.enabled and self.params.continuous_recording_enabled):
            self.recorder = None
            return
        if backend.lower().startswith("opencv"):
            self.init_for_opencv(source_meta)
        else:
            # This manager is OpenCV-only; other backends should use RecorderManager or pipeline-integrated recording.
            self.recorder = None

    def stop(self) -> None:
        if self.recorder:
            try:
                self.recorder.stop()
            except Exception:
                pass
            self.recorder = None