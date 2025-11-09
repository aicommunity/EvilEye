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

    # Get project root (go up from tests/integration/capture/opencv/ to project root)
    repo_root = Path(__file__).resolve().parents[4]
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
            "min_file_size_kb": 0,  # Don't delete small files in test
            "out_dir": str(tmp_path),
            "filename_tmpl": "{source_name}_{start_time}_{seq}.{ext}",
        },
    )
    assert cap.init() is True

    cap.start()
    # Wait a bit for threads to start and recorder to initialize
    time.sleep(0.5)
    
    # Check if recorder_manager was created
    assert cap.recorder_manager is not None, "RecorderManager should be created"
    assert cap.recorder_manager.recorder is not None, "Recorder should be created"
    
    # Get some frames to trigger recording
    # This ensures frames are processed and fed to the recorder
    frames_received = 0
    for _ in range(20):
        frames = cap.get()
        if frames:
            frames_received += len(frames)
            if frames_received >= 5:  # Get at least 5 frames
                break
        time.sleep(0.1)
    
    assert frames_received > 0, "No frames were received"
    
    # Wait a bit more to ensure frames are written
    time.sleep(2.0)
    
    cap.stop()
    
    # Wait for threads to finish and recorder to close files
    # Note: check_and_delete_small_files has min_age_seconds=30, so files won't be deleted immediately
    time.sleep(1.0)

    # Verify a file was written into daily subfolder
    # Check all subdirectories (date folders)
    date_dirs = list(tmp_path.glob("*/"))
    assert len(date_dirs) > 0, f"Daily folder not created in {tmp_path}"
    
    # Check for files in all date directories
    files = []
    for date_dir in date_dirs:
        files.extend(list(date_dir.glob("*.mp4")))
        files.extend(list(date_dir.glob("*.mkv")))  # Also check for mkv if mp4 codec failed
    
    # Also check in subdirectories (camera folders)
    for date_dir in date_dirs:
        camera_dirs = list(date_dir.glob("*/"))
        for camera_dir in camera_dirs:
            files.extend(list(camera_dir.glob("*.mp4")))
            files.extend(list(camera_dir.glob("*.mkv")))
    
    assert len(files) >= 1, f"No recording files created. Checked: {tmp_path}, date_dirs: {date_dirs}, files: {files}"
