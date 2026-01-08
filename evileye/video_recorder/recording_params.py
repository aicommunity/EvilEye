from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any


@dataclass
class RecordingParams:
    """Parameters controlling video recording.

    All time units in seconds; space threshold as percent [0-100].
    """

    enabled: bool = False
    container: str = "mp4"
    segment_length_sec: int = 300
    retention_days: int = 3
    min_free_space_pct: int = 80
    min_file_size_kb: int = 500  # Minimum file size in KB, files smaller will be deleted
    out_dir: str = "videos/recordings"
    filename_tmpl: str = "{source_name}_{start_time}_{seq}.{ext}"
    
    # Continuous recording settings
    continuous_recording_enabled: bool = False  # Enable continuous recording from all cameras
    
    # Event-based recording settings
    event_recording_enabled: bool = False  # Enable recording of video clips around events
    event_pre_seconds: int = 10  # Seconds before event to save
    event_post_seconds: int = 10  # Seconds after event to save
    event_buffer_fps: Optional[float] = None  # FPS for event buffer (None = use source FPS)
    
    # Video validation settings
    validate_video_integrity: bool = True  # Enable video file integrity validation
    video_validation_timeout: float = 2.0  # Timeout for video validation in seconds

    @staticmethod
    def from_config(config: Dict[str, Any] | None) -> "RecordingParams":
        if not config:
            return RecordingParams()
        record_cfg = config.get("record") if isinstance(config, dict) else None
        if isinstance(record_cfg, dict):
            event_buffer_fps = record_cfg.get("event_buffer_fps")
            if event_buffer_fps is not None:
                event_buffer_fps = float(event_buffer_fps)
            return RecordingParams(
                enabled=bool(record_cfg.get("enabled", False)),
                container=str(record_cfg.get("container", "mp4")),
                segment_length_sec=int(record_cfg.get("segment_length_sec", 300)),
                retention_days=int(record_cfg.get("retention_days", 3)),
                min_free_space_pct=int(record_cfg.get("min_free_space_pct", 80)),
                min_file_size_kb=int(record_cfg.get("min_file_size_kb", 500)),
                out_dir=str(record_cfg.get("out_dir", "videos/recordings")),
                filename_tmpl=str(record_cfg.get("filename_tmpl", "{source_name}_{start_time}_{seq}.{ext}")),
                continuous_recording_enabled=bool(record_cfg.get("continuous_recording_enabled", False)),
                event_recording_enabled=bool(record_cfg.get("event_recording_enabled", False)),
                event_pre_seconds=int(record_cfg.get("event_pre_seconds", 10)),
                event_post_seconds=int(record_cfg.get("event_post_seconds", 10)),
                event_buffer_fps=event_buffer_fps,
                validate_video_integrity=bool(record_cfg.get("validate_video_integrity", True)),
                video_validation_timeout=float(record_cfg.get("video_validation_timeout", 2.0)),
            )
        # Config may place record at top-level already
        cfg = config
        event_buffer_fps = cfg.get("event_buffer_fps")
        if event_buffer_fps is not None:
            event_buffer_fps = float(event_buffer_fps)
        return RecordingParams(
            enabled=bool(cfg.get("enabled", False)),
            container=str(cfg.get("container", "mp4")),
            segment_length_sec=int(cfg.get("segment_length_sec", 300)),
            retention_days=int(cfg.get("retention_days", 3)),
            min_free_space_pct=int(cfg.get("min_free_space_pct", 80)),
            min_file_size_kb=int(cfg.get("min_file_size_kb", 500)),
            out_dir=str(cfg.get("out_dir", "videos/recordings")),
            filename_tmpl=str(cfg.get("filename_tmpl", "{source_name}_{start_time}_{seq}.{ext}")),
            continuous_recording_enabled=bool(cfg.get("continuous_recording_enabled", False)),
            event_recording_enabled=bool(cfg.get("event_recording_enabled", False)),
            event_pre_seconds=int(cfg.get("event_pre_seconds", 10)),
            event_post_seconds=int(cfg.get("event_post_seconds", 10)),
            event_buffer_fps=event_buffer_fps,
            validate_video_integrity=bool(cfg.get("validate_video_integrity", True)),
            video_validation_timeout=float(cfg.get("video_validation_timeout", 2.0)),
        )

    def merge_overrides(self, overrides: Optional[Dict[str, Any]]) -> "RecordingParams":
        if not overrides:
            return self
        event_buffer_fps = overrides.get("event_buffer_fps", self.event_buffer_fps)
        if event_buffer_fps is not None:
            event_buffer_fps = float(event_buffer_fps)
        merged = RecordingParams(
            enabled=bool(overrides.get("enabled", self.enabled)),
            container=str(overrides.get("container", self.container)),
            segment_length_sec=int(overrides.get("segment_length_sec", self.segment_length_sec)),
            retention_days=int(overrides.get("retention_days", self.retention_days)),
            min_free_space_pct=int(overrides.get("min_free_space_pct", self.min_free_space_pct)),
            min_file_size_kb=int(overrides.get("min_file_size_kb", self.min_file_size_kb)),
            out_dir=str(overrides.get("out_dir", self.out_dir)),
            filename_tmpl=str(overrides.get("filename_tmpl", self.filename_tmpl)),
            continuous_recording_enabled=bool(overrides.get("continuous_recording_enabled", self.continuous_recording_enabled)),
            event_recording_enabled=bool(overrides.get("event_recording_enabled", self.event_recording_enabled)),
            event_pre_seconds=int(overrides.get("event_pre_seconds", self.event_pre_seconds)),
            event_post_seconds=int(overrides.get("event_post_seconds", self.event_post_seconds)),
            event_buffer_fps=event_buffer_fps,
            validate_video_integrity=bool(overrides.get("validate_video_integrity", self.validate_video_integrity)),
            video_validation_timeout=float(overrides.get("video_validation_timeout", self.video_validation_timeout)),
        )
        return merged

    def ensure_out_dir(self) -> Path:
        path = Path(self.out_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path


