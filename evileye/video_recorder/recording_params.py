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

    @staticmethod
    def from_config(config: Dict[str, Any] | None) -> "RecordingParams":
        if not config:
            return RecordingParams()
        record_cfg = config.get("record") if isinstance(config, dict) else None
        if isinstance(record_cfg, dict):
            return RecordingParams(
                enabled=bool(record_cfg.get("enabled", False)),
                container=str(record_cfg.get("container", "mp4")),
                segment_length_sec=int(record_cfg.get("segment_length_sec", 300)),
                retention_days=int(record_cfg.get("retention_days", 3)),
                min_free_space_pct=int(record_cfg.get("min_free_space_pct", 80)),
                min_file_size_kb=int(record_cfg.get("min_file_size_kb", 500)),
                out_dir=str(record_cfg.get("out_dir", "videos/recordings")),
                filename_tmpl=str(record_cfg.get("filename_tmpl", "{source_name}_{start_time}_{seq}.{ext}")),
            )
        # Config may place record at top-level already
        cfg = config
        return RecordingParams(
            enabled=bool(cfg.get("enabled", False)),
            container=str(cfg.get("container", "mp4")),
            segment_length_sec=int(cfg.get("segment_length_sec", 300)),
            retention_days=int(cfg.get("retention_days", 3)),
            min_free_space_pct=int(cfg.get("min_free_space_pct", 80)),
            min_file_size_kb=int(cfg.get("min_file_size_kb", 500)),
            out_dir=str(cfg.get("out_dir", "videos/recordings")),
            filename_tmpl=str(cfg.get("filename_tmpl", "{source_name}_{start_time}_{seq}.{ext}")),
        )

    def merge_overrides(self, overrides: Optional[Dict[str, Any]]) -> "RecordingParams":
        if not overrides:
            return self
        merged = RecordingParams(
            enabled=bool(overrides.get("enabled", self.enabled)),
            container=str(overrides.get("container", self.container)),
            segment_length_sec=int(overrides.get("segment_length_sec", self.segment_length_sec)),
            retention_days=int(overrides.get("retention_days", self.retention_days)),
            min_free_space_pct=int(overrides.get("min_free_space_pct", self.min_free_space_pct)),
            min_file_size_kb=int(overrides.get("min_file_size_kb", self.min_file_size_kb)),
            out_dir=str(overrides.get("out_dir", self.out_dir)),
            filename_tmpl=str(overrides.get("filename_tmpl", self.filename_tmpl)),
        )
        return merged

    def ensure_out_dir(self) -> Path:
        path = Path(self.out_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path


