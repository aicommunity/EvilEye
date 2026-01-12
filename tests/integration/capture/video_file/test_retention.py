from pathlib import Path
import time


def test_retention_enforce(tmp_path: Path):
    from evileye.video_recorder.retention import RetentionEnforcer
    from evileye.video_recorder.recording_params import RecordingParams

    # Create fake old/new files
    # RetentionEnforcer looks for files in base/date_dir/camera_dir/ or base/date_dir/
    # The code checks files in date_dir only if there are camera_dir subdirectories
    # So we create a camera_dir to ensure files are found
    rec_dir = tmp_path / "Recording" / time.strftime("%Y-%m-%d")
    rec_dir.mkdir(parents=True, exist_ok=True)
    camera_dir = rec_dir / "camera1"
    camera_dir.mkdir(exist_ok=True)
    
    old_file = camera_dir / "old.mp4"
    new_file = camera_dir / "new.mp4"
    old_file.write_bytes(b"0" * 1024)
    new_file.write_bytes(b"1" * 1024)

    # Make old_file older than retention cutoff
    old_time = time.time() - 5 * 24 * 3600  # 5 days ago
    new_time = time.time()
    os_utime = __import__("os").utime
    os_utime(str(old_file), (old_time, old_time))
    os_utime(str(new_file), (new_time, new_time))

    params = RecordingParams(
        enabled=True,
        container="mp4",
        segment_length_sec=300,
        retention_days=3,  # Files older than 3 days should be deleted
        min_free_space_pct=0,
        min_file_size_kb=0,  # Don't delete small files
        out_dir=str(tmp_path / "Recording"),
    )

    RetentionEnforcer().enforce(params)

    # Old file (5 days old) should be removed (older than 3 days retention)
    # New file (current time) should remain
    assert not old_file.exists(), f"Old file should be removed by retention (age: 5 days > 3 days retention). File exists: {old_file.exists()}, path: {old_file}"
    assert new_file.exists(), "New file should remain"
