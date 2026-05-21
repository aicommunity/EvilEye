"""Event-based recording setup (EventBuffer / EventRecorder per source)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from evileye.core.interfaces import IPipeline
from evileye.core.logger import get_module_logger


class EventRecordingService:
    """Initialize event recording buffers and recorders for pipeline sources."""

    def __init__(self):
        self.logger = get_module_logger("event_recording_service")

    def initialize_event_recording(
        self,
        host: Any,
        params: Dict[str, Any],
        pipeline: IPipeline,
        *,
        events_processor: Optional[Any] = None,
        on_event_recording: Optional[Callable] = None,
    ) -> None:
        """Populate host.event_buffers, host.event_recorders, host.recording_params."""
        try:
            from evileye.video_recorder.recording_params import RecordingParams
            from evileye.video_recorder.event_buffer import EventBuffer
            from evileye.video_recorder.event_recorder import EventRecorder
            from evileye.video_recorder.recorder_base import SourceMeta

            host.recording_params = RecordingParams.from_config(params)

            db_image_dir = ((params or {}).get("database", {}) or {}).get("image_dir") or "EvilEyeData"
            image_dir_path = Path(db_image_dir)
            if image_dir_path.is_absolute():
                host.recording_params.out_dir = str(image_dir_path)
            else:
                host.recording_params.out_dir = str(image_dir_path.resolve())
            self.logger.info(
                "Event recording out_dir set to database.image_dir: %s",
                host.recording_params.out_dir,
            )

            try:
                ok, reason = host.recording_params.check_out_dir_writable()
                if not ok:
                    host.recording_params.enabled = False
                    host.recording_params.continuous_recording_enabled = False
                    host.recording_params.event_recording_enabled = False
                    self.logger.warning(
                        "Recording disabled because out_dir is not writable/available: %s (reason: %s)",
                        host.recording_params.out_dir,
                        reason,
                    )
            except Exception:
                pass

            if not (
                host.recording_params.enabled
                and host.recording_params.event_recording_enabled
            ):
                self.logger.info("Event-based recording is disabled")
                return

            sources = pipeline.get_sources()
            if not sources:
                self.logger.warning("No sources found, event recording disabled")
                return

            max_buffer_duration = (
                host.recording_params.event_pre_seconds
                + host.recording_params.event_post_seconds
                + 5.0
            )

            for source in sources:
                if not source.source_ids:
                    continue

                source_id = source.source_ids[0]
                source_name = (
                    source.source_names[0]
                    if source.source_names
                    else f"source_{source_id}"
                )

                buffer_fps = host.recording_params.event_buffer_fps
                if buffer_fps is None:
                    try:
                        max_buf_fps = float(
                            os.environ.get("EVILEYE_EVENT_BUFFER_FPS_MAX", "5") or 5.0
                        )
                    except Exception:
                        max_buf_fps = 5.0
                    try:
                        src_fps = float(source.source_fps) if source.source_fps else 25.0
                    except Exception:
                        src_fps = 25.0
                    buffer_fps = min(src_fps, max_buf_fps)

                host.event_buffers[source_id] = EventBuffer(max_buffer_duration, buffer_fps)

                source_meta = SourceMeta(
                    source_name=source_name,
                    source_address=source.source_address,
                    source_type=str(source.source_type) if source.source_type else "unknown",
                    width=None,
                    height=None,
                    fps=buffer_fps,
                    username=source.username,
                    password=source.password,
                    source_names=source.source_names,
                    source_ids=source.source_ids,
                )
                host.event_recorders[source_id] = EventRecorder(
                    source_meta, host.recording_params, host.event_buffers[source_id]
                )
                self.logger.info(
                    "Initialized event recording for source %s (%s): buffer_duration=%ss, fps=%s",
                    source_id,
                    source_name,
                    max_buffer_duration,
                    buffer_fps,
                )

            if events_processor and on_event_recording:
                events_processor.set_event_recording_callback(on_event_recording)
                self.logger.info("Event recording callback registered with EventsProcessor")

        except Exception as e:
            self.logger.error("Failed to initialize event recording: %s", e, exc_info=True)
            host.event_buffers.clear()
            host.event_recorders.clear()
