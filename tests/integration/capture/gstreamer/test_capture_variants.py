import time
from pathlib import Path

import pytest


def _make_record_cfg(tmp_path: Path) -> dict:
    return {
        "enabled": True,
        "container": "mp4",
        "segment_length_sec": 60,
        "retention_days": 1,
        "min_free_space_pct": 0,
        "min_file_size_kb": 0,
        "out_dir": str(tmp_path),
        "filename_tmpl": "{source_name}_{start_time}_{seq}.{ext}",
    }


@pytest.fixture(scope="module")
def require_gst():
    try:
        import gi  # noqa: F401
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst  # noqa: F401
    except Exception:
        pytest.skip("GStreamer недоступен для тестов GStreamer backend")


@pytest.mark.usefixtures("require_gst", "require_gst_recording_elements")
@pytest.mark.parametrize("variant", ["VideoFile", "IpCamera", "Device", "ImageSequence"])
def test_gstreamer_capture_and_record_variants(
    variant,
    tmp_path: Path,
    request: pytest.FixtureRequest,
):
    from evileye.capture.video_capture_gstreamer import VideoCaptureGStreamer

    cap = VideoCaptureGStreamer()

    if variant == "VideoFile":
        source = "VideoFile"
        camera = request.getfixturevalue("test_video_mp4")
    elif variant == "IpCamera":
        source = "IpCamera"
        camera = request.getfixturevalue("local_rtsp_server")
    elif variant == "Device":
        source = "Device"
        camera = request.getfixturevalue("v4l2_test_device")
    elif variant == "ImageSequence":
        source = "ImageSequence"
        camera = request.getfixturevalue("images_sequence")
    else:
        pytest.skip("Неизвестный вариант")

    params = dict(
        source=source,
        camera=camera,
        source_ids=[0],
        source_names=["CamTestGST"],
        desired_fps=15,
        record=_make_record_cfg(tmp_path),
    )
    if variant == "ImageSequence":
        params["loop_play"] = False

    cap.set_params(**params)

    # Для локальной RTSP камеры оставляем стандартный main loop; для остальных источников
    # можно отключить GLib-loop, чтобы избежать зависаний при завершении теста.
    if variant != "IpCamera":
        try:
            cap._start_main_loop = lambda: None
            cap._stop_main_loop = lambda: None
        except Exception:
            pass
    else:
        # Для IpCamera чаще надёжнее TCP в тестовой среде
        cap._rtsp_protocol = "tcp"

    init_ok = cap.init()
    if not init_ok:
        pytest.skip(f"Инициализация GStreamer для {variant} не удалась: {getattr(cap, '_last_init_error', None)}")
    cap.start()

    # Подождать и получить несколько кадров
    frames_received = 0
    for _ in range(60):
        frames = cap.get()
        if frames:
            frames_received += len(frames)
            if frames_received >= 5:
                break
        time.sleep(0.05)

    assert frames_received > 0, f"Кадры не получены для {variant}"

    # Дать времени записать фрагмент
    time.sleep(2.0)
    cap.stop()
    time.sleep(0.5)

    # Проверяем создание файла записи (локальная проверка, без импорта conftest)
    # Recording creates structure: out_dir/Streams/YYYY-MM-DD/CameraName/
    streams_dir = Path(tmp_path) / "Streams"
    if not streams_dir.exists():
        # Fallback: check direct subdirectories (old structure)
        date_dirs = list(Path(tmp_path).glob("*/"))
        assert len(date_dirs) > 0, f"Не создана папка с датой записи в {tmp_path}"
    else:
        # New structure: Streams/YYYY-MM-DD/CameraName/
        date_dirs = list(streams_dir.glob("*/"))
        assert len(date_dirs) > 0, f"Не создана папка с датой записи в {streams_dir}"
    
    files = []
    for date_dir in date_dirs:
        files.extend(list(date_dir.glob("*.mp4")))
        files.extend(list(date_dir.glob("*.mkv")))
        for camera_dir in date_dir.glob("*/"):
            files.extend(list(camera_dir.glob("*.mp4")))
            files.extend(list(camera_dir.glob("*.mkv")))
    assert len(files) >= 1, f"Файлы записи не найдены. Проверено: {tmp_path}, streams_dir: {streams_dir}, date_dirs: {date_dirs}"


