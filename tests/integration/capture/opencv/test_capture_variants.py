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
    # Recorder uses Streams/<date>/<camera>/..., so search the full tree.
    files = list(out_dir.rglob("*.mp4")) + list(out_dir.rglob("*.mkv"))
    assert files, f"Файлы записи не найдены в {out_dir}"


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


