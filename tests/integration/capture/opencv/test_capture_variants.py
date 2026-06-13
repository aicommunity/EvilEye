import time
from pathlib import Path

import pytest


def _make_record_cfg(tmp_path: Path) -> dict:
    return {
        "enabled": True,
        "continuous_recording_enabled": True,
        "container": "mp4",
        "segment_length_sec": 60,
        "retention_days": 1,
        "min_free_space_pct": 0,
        "min_file_size_kb": 0,
        "out_dir": str(tmp_path),
        "filename_tmpl": "{source_name}_{start_time}_{seq}.{ext}",
    }


def _assert_recording_created(out_dir: Path) -> None:
    # OpenCV recorder may write either directly into out_dir or into a date/camera hierarchy.
    files = []
    files.extend(list(out_dir.glob("*.mp4")))
    files.extend(list(out_dir.glob("*.mkv")))
    if files:
        return

    date_dirs = list(out_dir.glob("*/"))
    assert len(date_dirs) > 0, f"Не создана папка с датой записи в {out_dir}"
    for date_dir in date_dirs:
        files.extend(list(date_dir.glob("*.mp4")))
        files.extend(list(date_dir.glob("*.mkv")))
        for camera_dir in date_dir.glob("*/"):
            files.extend(list(camera_dir.glob("*.mp4")))
            files.extend(list(camera_dir.glob("*.mkv")))
    assert len(files) >= 1, f"Файлы записи не найдены. Проверено: {out_dir}, date_dirs: {date_dirs}"


@pytest.mark.parametrize("variant", ["VideoFile", "IpCamera", "Device"])
def test_opencv_capture_and_record_variants(variant, tmp_path: Path, request: pytest.FixtureRequest):
    from evileye.capture.video_capture_opencv import VideoCaptureOpencv

    cap = VideoCaptureOpencv()

    if variant == "VideoFile":
        source = "VideoFile"
        camera = request.getfixturevalue("test_video_mp4")
    elif variant == "IpCamera":
        source = "IpCamera"
        camera = request.getfixturevalue("local_rtsp_server")
    elif variant == "Device":
        source = "Device"
        camera = request.getfixturevalue("v4l2_test_device")
    else:
        pytest.skip("Неизвестный вариант")

    cap.set_params(
        source=source,
        camera=camera,
        source_ids=[0],
        source_names=["CamTest"],
        desired_fps=15,
        record=_make_record_cfg(tmp_path),
    )

    assert cap.init() is True
    cap.start()

    # Подождать и получить несколько кадров
    frames_received = 0
    for _ in range(50):
        frames = cap.get()
        if frames:
            frames_received += len(frames)
            if frames_received >= 5:
                break
        time.sleep(0.05)

    assert frames_received > 0, "Кадры не получены"

    # Дать времени записать фрагмент
    time.sleep(1.5)
    cap.stop()
    time.sleep(0.5)

    # Проверяем создание файла записи
    _assert_recording_created(Path(tmp_path))


