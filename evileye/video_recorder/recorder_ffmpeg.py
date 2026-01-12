from __future__ import annotations

import datetime as _dt
import os
import shlex
import subprocess
from pathlib import Path
from typing import Optional

from evileye.core.logger import get_module_logger
from evileye.video_recorder.recording_params import RecordingParams
from evileye.video_recorder.recorder_base import VideoRecorderBase, SourceMeta


class FfmpegRecorder(VideoRecorderBase):
    def __init__(self) -> None:
        super().__init__()
        self.logger = get_module_logger("recorder_ffmpeg")
        self._proc: Optional[subprocess.Popen] = None

    def _segment_pattern(self, start_dt: _dt.datetime) -> str:
        date_dir = start_dt.strftime("%Y-%m-%d")
        
        # Compose camera folder name from all source_names or source_ids
        if self.source and self.source.source_names and len(self.source.source_names) > 0:
            camera_folder = "-".join(self.source.source_names)
        elif self.source and self.source.source_ids and len(self.source.source_ids) > 0:
            camera_folder = "-".join(str(sid) for sid in self.source.source_ids)
        elif self.source:
            camera_folder = self.source.source_name
        else:
            camera_folder = "source"
        
        # Create path: out_dir/YYYY-MM-DD/CameraName/
        base_out_dir = Path(self.params.out_dir) if self.params.out_dir else Path(".")
        out_dir = base_out_dir / date_dir / camera_folder
        out_dir.mkdir(parents=True, exist_ok=True)
        
        ts = start_dt.strftime("%Y%m%d_%H%M%S")
        source_name = (self.source.source_names[0] if self.source and self.source.source_names else 
                       (self.source.source_name if self.source else "source"))
        name_stem = self.params.filename_tmpl.format(
            source_name=source_name,
            start_time=ts,
            seq=0,
            ext=self.params.container,
        )
        stem = (out_dir / name_stem).with_suffix("")
        return str(stem) + "_%05d." + self.params.container

    def start(self, source_meta: SourceMeta, params: RecordingParams) -> None:
        self.source = source_meta
        self.params = params
        start_dt = _dt.datetime.now()
        pattern = self._segment_pattern(start_dt)

        # Build ffmpeg command (copy streams, segment by time, reset timestamps)
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
            "-fflags", "+genpts",
            "-i", str(self.source.source_address),
            "-c", "copy",
            "-f", "segment",
            "-segment_time", str(int(self.params.segment_length_sec)),
            "-reset_timestamps", "1",
            pattern,
        ]
        self.logger.info(f"Starting ffmpeg recorder: {' '.join(shlex.quote(c) for c in cmd)}")
        # Inherit environment; ensure LANG set to avoid locale warnings
        env = os.environ.copy()
        try:
            self._proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.is_running = True
        except Exception as e:
            self.logger.error(f"Failed to start ffmpeg recorder: {e}")
            raise

    def rotate_segment(self) -> None:
        # ffmpeg handles rotation by time; nothing to do
        pass

    def stop(self) -> None:
        if not self.is_running:
            return
        try:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=3)
                except Exception:
                    self._proc.kill()
        finally:
            self._proc = None
            self.is_running = False


