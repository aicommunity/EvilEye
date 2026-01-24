"""
Unified path generator for recorder outputs.
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from evileye.video_recorder.recorder_base import SourceMeta
from evileye.video_recorder.recording_params import RecordingParams


class PathGenerator:
    @staticmethod
    def get_camera_folder(source: Optional[SourceMeta]) -> str:
        if source and source.source_names and len(source.source_names) > 0:
            return "-".join(source.source_names)
        if source and source.source_ids and len(source.source_ids) > 0:
            return "-".join(str(sid) for sid in source.source_ids)
        if source:
            return source.source_name
        return "source"

    @staticmethod
    def generate_stream_path(
        source: Optional[SourceMeta],
        params: RecordingParams,
        segment_started_ts: float,
        seq: int,
        use_pattern: bool = False,
    ) -> str:
        date_dir = time.strftime("%Y-%m-%d", time.localtime(segment_started_ts))
        camera_folder = PathGenerator.get_camera_folder(source)
        base_dir = Path(params.out_dir) if params.out_dir else Path("EvilEyeData")
        out_dir = base_dir / "Streams" / date_dir / camera_folder
        out_dir.mkdir(parents=True, exist_ok=True)

        ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(segment_started_ts))
        source_name = (
            source.source_names[0] if source and source.source_names else (source.source_name if source else "source")
        )
        name = params.filename_tmpl.format(
            source_name=source_name,
            start_time=ts,
            seq=seq,
            ext=params.container,
        )

        if use_pattern:
            stem = (out_dir / name).with_suffix("")
            return str(stem) + "_%05d." + params.container

        return str(out_dir / name)

    @staticmethod
    def generate_event_path(
        source: Optional[SourceMeta],
        params: RecordingParams,
        event_id: int,
        event_name: str,
        event_timestamp: float,
    ) -> Path:
        event_date = datetime.fromtimestamp(event_timestamp).strftime("%Y-%m-%d")
        event_time = datetime.fromtimestamp(event_timestamp).strftime("%Y%m%d_%H%M%S")
        camera_folder = PathGenerator.get_camera_folder(source)

        base_dir = Path(params.out_dir) if params.out_dir else Path("EvilEyeData")
        out_dir = base_dir / "Events" / event_date / "Videos" / camera_folder
        out_dir.mkdir(parents=True, exist_ok=True)

        source_name = (
            source.source_names[0] if source and source.source_names else (source.source_name if source else "source")
        )
        filename = f"{source_name}_{event_name}_{event_id}_{event_time}.{params.container}"
        return out_dir / filename

