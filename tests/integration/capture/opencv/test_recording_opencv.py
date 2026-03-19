import os
import time
from pathlib import Path

import pytest


def _find_existing_video(repo_root: Path, ensure_test_videos=None) -> str:
    """
    Находит существующее видео для тестов.
    Приоритет: файлы из deploy-samples (videos/), затем старые файлы из tests/data/videos/.
    """
    videos_dir = repo_root / "videos"
    test_videos_dir = repo_root / "tests" / "data" / "videos"
    
    # Приоритет 1: файлы из deploy-samples (videos/)
    deploy_samples_candidates = [
        videos_dir / "planes_sample.mp4",  # Основной тестовый файл из deploy-samples
        videos_dir / "sample_split.mp4",   # Альтернативный файл из deploy-samples
    ]
    for p in deploy_samples_candidates:
        if p.exists():
            return str(p)
    
    # Приоритет 2: любой mp4 в videos/ (из deploy-samples)
    if videos_dir.exists():
        for p in videos_dir.glob("*.mp4"):
            return str(p)
    
    # Приоритет 3: старые файлы из tests/data/videos/ (для обратной совместимости)
    if test_videos_dir.exists():
        for p in test_videos_dir.glob("*.mp4"):
            # Пропустить файлы помеченные для удаления
            if not p.name.startswith("!del_"):
                return str(p)
    
    pytest.skip("No sample mp4 found in repository to test recording. "
                "Run 'evileye deploy-samples' to download test videos.")


def test_opencv_recording_basic(tmp_path: Path, ensure_test_videos):
    from evileye.capture.video_capture_opencv import VideoCaptureOpencv

    # Get project root (go up from tests/integration/capture/opencv/ to project root)
    repo_root = Path(__file__).resolve().parents[4]
    video_path = _find_existing_video(repo_root, ensure_test_videos)

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
            "continuous_recording_enabled": True,
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

    # Verify at least one recording file exists.
    # OpenCV recorder can write either directly into out_dir or into a hierarchy.
    files = []
    files.extend(list(tmp_path.glob("*.mp4")))
    files.extend(list(tmp_path.glob("*.mkv")))
    if not files:
        # Try hierarchy: Streams/... or legacy date/camera structure
        files.extend(list(tmp_path.rglob("*.mp4")))
        files.extend(list(tmp_path.rglob("*.mkv")))
    assert len(files) >= 1, f"No recording files created. Checked recursively under: {tmp_path}"
