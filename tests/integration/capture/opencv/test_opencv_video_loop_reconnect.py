import time
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def require_opencv():
    try:
        import cv2  # noqa: F401
    except Exception:
        pytest.skip("OpenCV недоступен для тестов OpenCV backend")


@pytest.mark.usefixtures("require_opencv")
def test_opencv_video_loop_reconnect_single(
    test_video_mp4,
    tmp_path: Path,
):
    """
    Тест реконнекта одного видеофайла с loop_play при завершении видео для OpenCV backend.
    Проверяет, что после завершения видео оно перезапускается и продолжает отправлять кадры.
    """
    from evileye.capture.video_capture_opencv import VideoCaptureOpencv
    from evileye.capture.video_capture_base import CaptureDeviceType

    cap = VideoCaptureOpencv()
    
    params = dict(
        source="VideoFile",
        camera=test_video_mp4,
        source_ids=[0],
        source_names=["TestCam"],
        desired_fps=15,
        loop_play=True,  # Включить зацикливание
        apiPreference="CAP_FFMPEG",
    )
    
    cap.set_params(**params)
    
    # Инициализация
    init_ok = cap.init()
    assert init_ok, f"Инициализация не удалась"
    assert cap.is_inited, "is_inited должен быть True после успешной инициализации"
    assert cap.is_working, "is_working должен быть True после успешной инициализации"
    
    cap.start()
    
    # Получить несколько кадров до завершения видео
    frames_before_eos = []
    for _ in range(30):  # Получаем кадры до EOS (видео длится ~3 секунды при 15 fps)
        frames = cap.get()
        if frames:
            frames_before_eos.extend(frames)
        time.sleep(0.1)
        if len(frames_before_eos) >= 10:  # Получили достаточно кадров
            break
    
    assert len(frames_before_eos) > 0, "Должны быть получены кадры до завершения видео"
    initial_frame_count = len(frames_before_eos)
    
    # Ждем завершения видео и перезапуска
    # Видео длится ~3 секунды, ждем немного больше для обработки reset()
    time.sleep(5.0)
    
    # Проверяем, что после завершения видео оно перезапустилось и продолжает отправлять кадры
    frames_after_eos = []
    reconnect_detected = False
    
    for _ in range(60):  # Проверяем в течение 6 секунд
        frames = cap.get()
        if frames:
            frames_after_eos.extend(frames)
            # Проверяем, что получили новые кадры после перезапуска
            if len(frames_after_eos) > 0:
                reconnect_detected = True
        
        # Проверяем состояние
        if cap.is_inited and cap.is_working:
            reconnect_detected = True
        
        time.sleep(0.1)
        
        if reconnect_detected and len(frames_after_eos) >= 5:
            break
    
    cap.stop()
    time.sleep(0.5)
    
    # Проверки
    assert reconnect_detected, "Реконнект должен был произойти после завершения видео"
    assert cap.is_inited, "is_inited должен быть True после реконнекта"
    assert cap.is_working, "is_working должен быть True после реконнекта"
    assert len(frames_after_eos) > 0, "Должны быть получены кадры после реконнекта"
    
    # Проверяем, что получили кадры из нового цикла
    if frames_after_eos:
        first_frame_after = frames_after_eos[0]
        assert hasattr(first_frame_after, 'image'), "Кадр должен содержать изображение"


@pytest.mark.usefixtures("require_opencv")
def test_opencv_video_loop_reconnect_multiple(
    test_video_mp4,
    tmp_path: Path,
):
    """
    Тест реконнекта множественных источников с loop_play для OpenCV backend.
    Симулирует ситуацию из poly-videos-gst.json с несколькими источниками.
    """
    from evileye.capture.video_capture_opencv import VideoCaptureOpencv
    
    # Создаем несколько источников с одним и тем же видеофайлом
    num_sources = 3
    sources = []
    
    for i in range(num_sources):
        cap = VideoCaptureOpencv()
        params = dict(
            source="VideoFile",
            camera=test_video_mp4,
            source_ids=[i],
            source_names=[f"TestCam{i}"],
            desired_fps=15,
            loop_play=True,
            apiPreference="CAP_FFMPEG",
        )
        cap.set_params(**params)
        
        init_ok = cap.init()
        assert init_ok, f"Инициализация источника {i} не удалась"
        assert cap.is_inited, f"is_inited должен быть True для источника {i}"
        assert cap.is_working, f"is_working должен быть True для источника {i}"
        
        cap.start()
        sources.append(cap)
    
    # Получаем кадры от всех источников
    all_frames = {i: [] for i in range(num_sources)}
    
    for _ in range(30):
        for i, cap in enumerate(sources):
            frames = cap.get()
            if frames:
                all_frames[i].extend(frames)
        time.sleep(0.1)
        if all(len(frames) >= 5 for frames in all_frames.values()):
            break
    
    # Проверяем, что все источники отправляют кадры
    for i, frames in all_frames.items():
        assert len(frames) > 0, f"Источник {i} должен отправлять кадры"
    
    # Ждем завершения видео для всех источников
    time.sleep(5.0)
    
    # Проверяем реконнект для всех источников
    frames_after_eos = {i: [] for i in range(num_sources)}
    reconnect_detected = {i: False for i in range(num_sources)}
    
    for _ in range(60):
        for i, cap in enumerate(sources):
            frames = cap.get()
            if frames:
                frames_after_eos[i].extend(frames)
                if len(frames_after_eos[i]) > 0:
                    reconnect_detected[i] = True
            
            # Проверяем состояние
            if cap.is_inited and cap.is_working:
                reconnect_detected[i] = True
        
        time.sleep(0.1)
        
        if all(reconnect_detected.values()) and all(len(frames) >= 3 for frames in frames_after_eos.values()):
            break
    
    # Останавливаем все источники
    for cap in sources:
        cap.stop()
    time.sleep(0.5)
    
    # Проверки для всех источников
    for i in range(num_sources):
        assert reconnect_detected[i], f"Реконнект должен был произойти для источника {i}"
        assert sources[i].is_inited, f"is_inited должен быть True для источника {i} после реконнекта"
        assert sources[i].is_working, f"is_working должен быть True для источника {i} после реконнекта"
        assert len(frames_after_eos[i]) > 0, f"Должны быть получены кадры после реконнекта для источника {i}"
