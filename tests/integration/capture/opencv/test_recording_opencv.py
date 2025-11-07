import os
import time
from pathlib import Path

import pytest


def _find_existing_video(repo_root: Path) -> str:
    # Prefer known sample files at repo root
    candidates = [
        repo_root / "12635-video-trim.mp4",
        repo_root / "139932-video_trim.mp4",
        repo_root / "40374-video_trim.mp4",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    # fallback: any mp4 under videos/
    for p in (repo_root / "videos").glob("**/*.mp4"):
        return str(p)
    pytest.skip("No sample mp4 found in repository to test recording")


def test_opencv_recording_basic(tmp_path: Path):
    from evileye.capture.video_capture_opencv import VideoCaptureOpencv

    repo_root = Path(__file__).resolve().parents[1]
    video_path = _find_existing_video(repo_root)

    cap = VideoCaptureOpencv()
    # Minimal params to start capture and enable recording
    cap.set_params(
        source="VideoFile",
        camera=video_path,
        source_ids=[0],
        source_names=["CamTest"],
        desired_fps=15,
        record={
            "enabled": True,
            "container": "mp4",
            "segment_length_sec": 300,
            "retention_days": 3,
            "min_free_space_pct": 0,  # ignore for test
            "out_dir": str(tmp_path),
            "filename_tmpl": "{source_name}_{start_time}_{seq}.{ext}",
        },
    )
    assert cap.init() is True

    cap.start()
    # Wait a bit to grab and retrieve frames
    time.sleep(2.5)
    cap.stop()

    # Verify a file was written into daily subfolder
    date_dir = next(tmp_path.glob("*/"), None)
    assert date_dir is not None, "Daily folder not created"
    files = list(Path(date_dir).glob("*.mp4"))
    assert len(files) >= 1, "No recording files created"
