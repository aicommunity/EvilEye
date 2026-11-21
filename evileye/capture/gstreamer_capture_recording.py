"""GStreamer continuous recording branch lifecycle."""

from __future__ import annotations

from .gstreamer_capture_common import Gst, GstContinuousRecorder, SourceMeta


class _RecordingFilesystemError(RuntimeError):
    """Raised when the configured recording destination is unavailable."""


class GStreamerCaptureRecordingMixin:
    def _setup_recording_branch(self) -> None:
        """Attach the shared recorder to the capture pipeline's recording queue."""
        params = self.recording_params
        if not (
            params
            and params.enabled
            and params.continuous_recording_enabled
        ):
            return

        recording_queue = self.pipeline.get_by_name("recording_queue")
        if recording_queue is None:
            raise RuntimeError(
                "Continuous recording is enabled but the pipeline has no recording_queue"
            )

        source_name = self.source_names[0] if self.source_names else "source"
        source = SourceMeta(
            source_name=source_name,
            source_address=self.source_address,
            source_type=str(self.source_type),
            width=None,
            height=None,
            fps=self.source_fps,
            source_names=self.source_names,
            source_ids=self.source_ids,
        )
        recorder = self._gst_continuous_recorder
        if recorder is None:
            recorder = GstContinuousRecorder()
            self._gst_continuous_recorder = recorder

        recorder.start(source, params)
        self._recording_queue_elem = recording_queue
        try:
            recorder.start_with_pipeline(
                pipeline=self.pipeline,
                recording_queue_elem=recording_queue,
                Gst=Gst,
            )
        except OSError as exc:
            raise _RecordingFilesystemError(str(exc)) from exc

        if recorder._refs is None:
            raise RuntimeError(
                "Continuous recording was enabled but no recording branch was attached"
            )

    def _cleanup_recording_branch(self, *, pipeline=None) -> None:
        """Finalize and detach the shared recorder branch."""
        active_pipeline = self.pipeline if pipeline is None else pipeline
        recorder = self._gst_continuous_recorder
        if recorder is None or active_pipeline is None or recorder._refs is None:
            self._recording_queue_elem = None
            return

        recorder.stop_with_pipeline(pipeline=active_pipeline, Gst=Gst)
        self._recording_queue_elem = None
