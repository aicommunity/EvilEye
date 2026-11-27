"""VideoValidator must not delete large unfinalized splitmux fragments."""

from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

from evileye.video_recorder.video_validator import VideoValidator


def test_video_validator_keeps_large_unfinalized_splitmux(tmp_path: Path, monkeypatch):
    day = tmp_path / "2026-11-22" / "Cam4-Cam5"
    day.mkdir(parents=True)
    fragment = day / "Cam4_20261122_230557_0_00000.mp4"
    # Large enough to pass min_size; includes accidental moov bytes in payload.
    fragment.write_bytes(b"XXXX" + b"moov" + b"YYYY" + b"\x00" * (64 * 1024))
    old = time.time() - 600
    os.utime(fragment, (old, old))

    params = SimpleNamespace(
        out_dir=str(tmp_path),
        container="mp4",
        validate_video_integrity=True,
        video_validation_timeout=0.5,
        min_file_size_kb=1,
    )
    validator = VideoValidator(params, check_interval_seconds=60, min_file_age_seconds=60)
    # Force OpenCV path to claim "corrupt" so the old validator would have deleted it.
    monkeypatch.setattr(
        "evileye.video_recorder.file_validator.FileValidator.is_file_valid",
        lambda *_args, **_kwargs: False,
    )

    validator._validate_all_files()

    assert fragment.exists(), "unfinalized splitmux fragment must not be deleted"
