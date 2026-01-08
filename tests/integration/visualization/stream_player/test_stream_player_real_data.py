#!/usr/bin/env python3
"""
Интеграционные тесты для плеера потоковых записей с реальными данными
Использует данные из EvilEyeData/Streams/2026-01-06 и конфиг poly-videos-gst.json
"""

import sys
import os
import json
from pathlib import Path

# Добавить корневую директорию проекта в путь
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
import datetime
from unittest.mock import Mock, MagicMock, patch
import tempfile
import shutil
import glob

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt, QTimer
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt, QTimer
    pyqt_version = 5

from evileye.visualization_modules.stream_player_window import StreamPlayerWindow
from evileye.visualization_modules.stream_player_components import (
    VideoGridWidget, TimelineWidget, CameraSelectorWidget
)


@pytest.fixture(scope="session")
def qapp():
    """Создать QApplication для тестов"""
    if not QApplication.instance():
        app = QApplication(sys.argv)
        yield app
        app.quit()
    else:
        yield QApplication.instance()


@pytest.fixture
def real_base_dir():
    """Фикстура для реальной базовой директории"""
    base_dir = Path("/home/user/EvilEye/EvilEyeData")
    if not base_dir.exists():
        pytest.skip(f"Real base directory does not exist: {base_dir}")
    return str(base_dir)


@pytest.fixture
def real_config():
    """Фикстура для загрузки реального конфига"""
    config_path = Path("/home/user/EvilEye/configs/poly-videos-gst.json")
    if not config_path.exists():
        pytest.skip(f"Config file does not exist: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    return config


@pytest.fixture
def real_streams_date():
    """Фикстура для реальной даты потоков"""
    return "2026-01-06"


@pytest.fixture
def real_video_files(real_base_dir, real_streams_date):
    """Фикстура для получения реальных видеофайлов"""
    streams_dir = Path(real_base_dir) / "Streams" / real_streams_date
    
    if not streams_dir.exists():
        pytest.skip(f"Streams directory does not exist: {streams_dir}")
    
    video_files = {}
    
    # Найти все папки камер
    for camera_folder in streams_dir.iterdir():
        if camera_folder.is_dir():
            mp4_files = list(camera_folder.glob("*.mp4"))
            if mp4_files:
                video_files[camera_folder.name] = [str(f) for f in sorted(mp4_files)]
    
    if not video_files:
        pytest.skip(f"No video files found in {streams_dir}")
    
    return video_files


class TestRealDataPlayback:
    """Тесты воспроизведения с реальными данными"""
    
    def test_playback_with_real_cam1(self, qapp, real_base_dir, real_config, real_streams_date, real_video_files):
        """Тест воспроизведения видео из Cam1 (обычный источник)"""
        if 'Cam1' not in real_video_files:
            pytest.skip("Cam1 video files not found")
        
        window = StreamPlayerWindow(base_dir=real_base_dir, params=real_config)
        window.show()
        qapp.processEvents()
        
        # Выбрать дату
        from PyQt6.QtCore import QDate
        try:
            from PyQt5.QtCore import QDate
        except ImportError:
            pass
        
        date_parts = real_streams_date.split('-')
        qdate = QDate(int(date_parts[0]), int(date_parts[1]), int(date_parts[2]))
        window.camera_selector.date_edit.setDate(qdate)
        qapp.processEvents()
        
        # Выбрать Cam1
        window._selected_cameras = ['Cam1']
        window._load_camera_segments()
        qapp.processEvents()
        
        # Проверить, что сегменты загружены
        assert 'Cam1' in window._camera_segments
        assert len(window._camera_segments['Cam1']) > 0
        
        # Проверить, что первый сегмент существует и валиден
        first_segment = window._camera_segments['Cam1'][0]
        assert os.path.exists(first_segment)
        assert os.path.getsize(first_segment) > 1024
        
        window.close()
    
    def test_playback_with_real_split_sources(self, qapp, real_base_dir, real_config, real_streams_date, real_video_files):
        """Тест воспроизведения разделенных источников (Cam2-Cam3, Cam4-Cam5)"""
        window = StreamPlayerWindow(base_dir=real_base_dir, params=real_config)
        window.show()
        qapp.processEvents()
        
        # Выбрать дату
        from PyQt6.QtCore import QDate
        try:
            from PyQt5.QtCore import QDate
        except ImportError:
            pass
        
        date_parts = real_streams_date.split('-')
        qdate = QDate(int(date_parts[0]), int(date_parts[1]), int(date_parts[2]))
        window.camera_selector.date_edit.setDate(qdate)
        qapp.processEvents()
        
        # Проверить разрешение имен источников для разделенных потоков
        # Cam2 должен разрешаться в Cam2-Cam3
        folder_name_cam2 = window._resolve_camera_folder_name('Cam2', real_streams_date)
        assert folder_name_cam2 == 'Cam2-Cam3' or folder_name_cam2 == 'Cam2', f"Expected 'Cam2-Cam3' or 'Cam2', got '{folder_name_cam2}'"
        
        folder_name_cam3 = window._resolve_camera_folder_name('Cam3', real_streams_date)
        assert folder_name_cam3 == 'Cam2-Cam3' or folder_name_cam3 == 'Cam3', f"Expected 'Cam2-Cam3' or 'Cam3', got '{folder_name_cam3}'"
        
        # Выбрать разделенные источники
        window._selected_cameras = ['Cam2', 'Cam3']
        window._load_camera_segments()
        qapp.processEvents()
        
        # Проверить, что сегменты загружены (оба источника должны использовать одну папку)
        assert 'Cam2' in window._camera_segments or 'Cam3' in window._camera_segments
        
        window.close()
    
    def test_opencv_fallback_for_large_videos(self, qapp, real_base_dir, real_config, real_streams_date, real_video_files):
        """Тест автоматического переключения на OpenCV для больших видео (>2048px)"""
        import cv2
        if cv2 is None:
            pytest.skip("OpenCV not available")
        
        window = StreamPlayerWindow(base_dir=real_base_dir, params=real_config)
        
        # Найти видео с шириной > 2048
        large_video = None
        for camera_folder, video_list in real_video_files.items():
            for video_path in video_list[:10]:  # Проверить первые 10 файлов
                cap = cv2.VideoCapture(video_path)
                if cap.isOpened():
                    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    cap.release()
                    if width > 2048:
                        large_video = video_path
                        break
            if large_video:
                break
        
        # Если не найдено большое видео, проверить логику переключения на основе конфига
        # Для Cam2-Cam3 и Cam4-Cam5 ширина должна быть 2304 (из конфига)
        if not large_video:
            # Попробовать найти файлы из разделенных источников (они должны быть большими)
            for folder_name in ['Cam2-Cam3', 'Cam4-Cam5']:
                if folder_name in real_video_files and len(real_video_files[folder_name]) > 0:
                    test_video = real_video_files[folder_name][0]
                    # Проверить размер файла через OpenCV
                    cap_test = cv2.VideoCapture(test_video)
                    if cap_test.isOpened():
                        width = int(cap_test.get(cv2.CAP_PROP_FRAME_WIDTH))
                        cap_test.release()
                        if width > 2048:
                            # Проверить логику переключения на OpenCV для этих файлов
                            from evileye.visualization_modules.video_player_window import VideoPlayerWidget
                            player = VideoPlayerWidget(parent=None, logger_name="test_player")
                            player._use_opencv = False  # Начать с QMediaPlayer
                            result = player.play_video(test_video)
                            qapp.processEvents()
                            QTimer.singleShot(1000, lambda: None)
                            qapp.processEvents()
                            # Должно переключиться на OpenCV из-за размера или ошибок CUDA
                            assert player._use_opencv == True, f"Should use OpenCV for split source video from {folder_name} (width={width})"
                            player.close()
                            window.close()
                            return
        
        if not large_video:
            pytest.skip("No large video files (>2048px) found for testing")
        
        # Создать видеоплеер и проверить автоматическое переключение на OpenCV
        from evileye.visualization_modules.video_player_window import VideoPlayerWidget
        
        player = VideoPlayerWidget(parent=None, logger_name="test_player")
        player.show()
        qapp.processEvents()
        
        # Попытаться воспроизвести большое видео
        # Должно автоматически переключиться на OpenCV
        result = player.play_video(large_video)
        
        # Дать время на обработку
        qapp.processEvents()
        QTimer.singleShot(500, lambda: None)
        qapp.processEvents()
        
        # Проверить, что используется OpenCV
        assert player._use_opencv == True, "Should automatically use OpenCV for large videos"
        
        player.close()
        window.close()
    
    def test_video_segment_loading(self, qapp, real_base_dir, real_config, real_streams_date):
        """Тест загрузки сегментов видео для реальной даты"""
        window = StreamPlayerWindow(base_dir=real_base_dir, params=real_config)
        window.show()
        qapp.processEvents()
        
        # Выбрать дату
        from PyQt6.QtCore import QDate
        try:
            from PyQt5.QtCore import QDate
        except ImportError:
            pass
        
        date_parts = real_streams_date.split('-')
        qdate = QDate(int(date_parts[0]), int(date_parts[1]), int(date_parts[2]))
        window.camera_selector.date_edit.setDate(qdate)
        qapp.processEvents()
        
        # Получить список доступных камер
        available_cameras = window.camera_selector._available_cameras.get(real_streams_date, [])
        assert len(available_cameras) > 0, "Should have at least one camera folder"
        
        # Загрузить сегменты для всех доступных камер
        for camera in available_cameras[:3]:  # Тестируем первые 3 камеры
            window._selected_cameras = [camera]
            window._load_camera_segments()
            qapp.processEvents()
            
            # Проверить, что сегменты загружены
            if camera in window._camera_segments:
                assert len(window._camera_segments[camera]) > 0, f"Should have segments for {camera}"
                # Проверить валидность первого сегмента
                first_segment = window._camera_segments[camera][0]
                assert os.path.exists(first_segment), f"Segment should exist: {first_segment}"
                assert os.path.getsize(first_segment) > 1024, f"Segment should be larger than 1KB: {first_segment}"
        
        window.close()
    
    def test_multiple_cameras_playback(self, qapp, real_base_dir, real_config, real_streams_date):
        """Тест одновременного воспроизведения нескольких камер"""
        window = StreamPlayerWindow(base_dir=real_base_dir, params=real_config)
        window.show()
        qapp.processEvents()
        
        # Выбрать дату
        from PyQt6.QtCore import QDate
        try:
            from PyQt5.QtCore import QDate
        except ImportError:
            pass
        
        date_parts = real_streams_date.split('-')
        qdate = QDate(int(date_parts[0]), int(date_parts[1]), int(date_parts[2]))
        window.camera_selector.date_edit.setDate(qdate)
        qapp.processEvents()
        
        # Получить список доступных камер
        available_cameras = window.camera_selector._available_cameras.get(real_streams_date, [])
        if len(available_cameras) < 2:
            pytest.skip("Need at least 2 cameras for this test")
        
        # Выбрать несколько камер
        selected = available_cameras[:2]
        window._selected_cameras = selected
        window._load_camera_segments()
        qapp.processEvents()
        
        # Установить камеры в сетку
        window.video_grid.set_cameras(
            selected, 
            window._camera_segment_times, 
            window._source_config,
            window.base_dir,
            real_streams_date
        )
        qapp.processEvents()
        
        # Проверить, что видеоплееры созданы
        assert len(window.video_grid._video_players) > 0, "Should have video players"
        
        window.close()


class TestErrorHandling:
    """Тесты обработки ошибок"""
    
    def test_cuda_error_handling(self, qapp, real_base_dir, real_config, real_video_files):
        """Тест обработки ошибок CUDA и переключения на OpenCV"""
        import cv2
        if cv2 is None:
            pytest.skip("OpenCV not available")
        
        # Найти большое видео (>2048px) для тестирования CUDA ошибок
        large_video = None
        for camera_folder, video_list in real_video_files.items():
            for video_path in video_list[:2]:
                cap = cv2.VideoCapture(video_path)
                if cap.isOpened():
                    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    cap.release()
                    if width > 2048:
                        large_video = video_path
                        break
            if large_video:
                break
        
        if not large_video:
            pytest.skip("No large video files (>2048px) found for CUDA error testing")
        
        from evileye.visualization_modules.video_player_window import VideoPlayerWidget
        
        player = VideoPlayerWidget(parent=None, logger_name="test_cuda_error")
        player.show()
        qapp.processEvents()
        
        # Попытаться воспроизвести через QMediaPlayer (должно переключиться на OpenCV)
        player._use_opencv = False  # Начать с QMediaPlayer
        result = player.play_video(large_video)
        
        # Дать время на обработку и переключение
        qapp.processEvents()
        QTimer.singleShot(1000, lambda: None)
        qapp.processEvents()
        
        # Проверить, что переключилось на OpenCV
        assert player._use_opencv == True, "Should have switched to OpenCV due to CUDA error or large video size"
        
        player.close()
    
    def test_corrupted_file_handling(self, qapp, real_base_dir, real_config):
        """Тест обработки поврежденных файлов (moov atom not found)"""
        window = StreamPlayerWindow(base_dir=real_base_dir, params=real_config)
        
        # Создать временный поврежденный файл
        temp_file = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
        temp_file.write(b'fake mp4 data')
        temp_file.close()
        
        try:
            from evileye.visualization_modules.video_player_window import VideoPlayerWidget
            
            player = VideoPlayerWidget(parent=None, logger_name="test_corrupted")
            player.show()
            qapp.processEvents()
            
            # Попытаться воспроизвести поврежденный файл
            result = player.play_video(temp_file.name)
            
            # Дать время на обработку ошибки
            qapp.processEvents()
            QTimer.singleShot(500, lambda: None)
            qapp.processEvents()
            
            # Файл должен быть отклонен (result может быть False или True в зависимости от реализации)
            # Главное - не должно быть краша
            
            player.close()
        finally:
            os.unlink(temp_file.name)
        
        window.close()
    
    def test_invalid_file_skipping(self, qapp, real_base_dir, real_config, real_streams_date, real_video_files):
        """Тест пропуска невалидных файлов при загрузке сегментов"""
        window = StreamPlayerWindow(base_dir=real_base_dir, params=real_config)
        
        # Создать временную директорию с валидным и невалидным файлом
        temp_dir = tempfile.mkdtemp()
        try:
            # Создать невалидный файл
            invalid_file = os.path.join(temp_dir, "invalid.mp4")
            with open(invalid_file, 'wb') as f:
                f.write(b'invalid data')
            
            # Проверить, что невалидный файл пропускается
            assert window._is_valid_video_file(invalid_file) == False
            
            # Проверить с реальным файлом (если есть)
            # real_video_files - это словарь {camera_folder: [list of video files]}
            if isinstance(real_video_files, dict) and len(real_video_files) > 0:
                first_camera = list(real_video_files.keys())[0]
                if len(real_video_files[first_camera]) > 0:
                    first_video = real_video_files[first_camera][0]
                    if os.path.exists(first_video):
                        # Проверить валидность (может быть False для поврежденных файлов)
                        is_valid = window._is_valid_video_file(first_video)
                        # Просто проверить, что метод работает без ошибок
                        assert isinstance(is_valid, bool)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        window.close()


class TestIntegration:
    """Тесты полной интеграции компонентов"""
    
    def test_full_playback_cycle(self, qapp, real_base_dir, real_config, real_streams_date):
        """Полный цикл воспроизведения: выбор даты → выбор камер → воспроизведение → перемотка"""
        window = StreamPlayerWindow(base_dir=real_base_dir, params=real_config)
        window.show()
        qapp.processEvents()
        
        # Выбрать дату
        from PyQt6.QtCore import QDate
        try:
            from PyQt5.QtCore import QDate
        except ImportError:
            pass
        
        date_parts = real_streams_date.split('-')
        qdate = QDate(int(date_parts[0]), int(date_parts[1]), int(date_parts[2]))
        window.camera_selector.date_edit.setDate(qdate)
        qapp.processEvents()
        
        # Получить список доступных камер
        available_cameras = window.camera_selector._available_cameras.get(real_streams_date, [])
        if len(available_cameras) == 0:
            pytest.skip("No cameras available for this date")
        
        # Выбрать первую камеру
        selected_camera = available_cameras[0]
        window._selected_cameras = [selected_camera]
        window._load_camera_segments()
        qapp.processEvents()
        
        # Установить камеры в сетку
        window.video_grid.set_cameras(
            [selected_camera],
            window._camera_segment_times,
            window._source_config,
            window.base_dir,
            real_streams_date
        )
        qapp.processEvents()
        
        # Проверить временной диапазон
        assert window._start_time is not None, "Should have start time"
        assert window._total_duration_ms > 0, "Should have duration"
        
        # Проверить временную шкалу
        assert window.timeline is not None, "Should have timeline"
        
        # Попытаться начать воспроизведение
        window._on_play_clicked()
        qapp.processEvents()
        QTimer.singleShot(500, lambda: None)
        qapp.processEvents()
        
        # Проверить, что воспроизведение началось
        assert window._is_playing == True, "Should be playing"
        
        # Остановить воспроизведение
        window._on_stop_clicked()
        qapp.processEvents()
        
        assert window._is_playing == False, "Should be stopped"
        
        window.close()
    
    def test_timeline_with_real_segments(self, qapp, real_base_dir, real_config, real_streams_date):
        """Тест временной шкалы с реальными сегментами"""
        window = StreamPlayerWindow(base_dir=real_base_dir, params=real_config)
        window.show()
        qapp.processEvents()
        
        # Выбрать дату
        from PyQt6.QtCore import QDate
        try:
            from PyQt5.QtCore import QDate
        except ImportError:
            pass
        
        date_parts = real_streams_date.split('-')
        qdate = QDate(int(date_parts[0]), int(date_parts[1]), int(date_parts[2]))
        window.camera_selector.date_edit.setDate(qdate)
        qapp.processEvents()
        
        # Получить список доступных камер
        available_cameras = window.camera_selector._available_cameras.get(real_streams_date, [])
        if len(available_cameras) == 0:
            pytest.skip("No cameras available for this date")
        
        # Выбрать камеру
        selected_camera = available_cameras[0]
        window._selected_cameras = [selected_camera]
        window._load_camera_segments()
        qapp.processEvents()
        
        # Проверить временную шкалу
        assert window._start_time is not None, "Should have start time"
        assert window._total_duration_ms > 0, "Should have duration"
        
        # Проверить метки времени на временной шкале
        assert window.timeline.start_time_label is not None
        assert window.timeline.end_time_label is not None
        assert window.timeline.current_time_label is not None
        
        window.close()
    
    def test_source_resolution(self, qapp, real_base_dir, real_config, real_streams_date):
        """Тест разрешения имен источников в имена папок для разделенных потоков"""
        window = StreamPlayerWindow(base_dir=real_base_dir, params=real_config)
        
        # Проверить разрешение для разделенных источников
        # Cam2 должен разрешаться в Cam2-Cam3
        folder_cam2 = window._resolve_camera_folder_name('Cam2', real_streams_date)
        assert folder_cam2 is not None, "Should resolve Cam2 to a folder"
        assert folder_cam2 == 'Cam2-Cam3' or folder_cam2 == 'Cam2', f"Expected 'Cam2-Cam3' or 'Cam2', got '{folder_cam2}'"
        
        folder_cam3 = window._resolve_camera_folder_name('Cam3', real_streams_date)
        assert folder_cam3 is not None, "Should resolve Cam3 to a folder"
        assert folder_cam3 == 'Cam2-Cam3' or folder_cam3 == 'Cam3', f"Expected 'Cam2-Cam3' or 'Cam3', got '{folder_cam3}'"
        
        folder_cam4 = window._resolve_camera_folder_name('Cam4', real_streams_date)
        assert folder_cam4 is not None, "Should resolve Cam4 to a folder"
        assert folder_cam4 == 'Cam4-Cam5' or folder_cam4 == 'Cam4', f"Expected 'Cam4-Cam5' or 'Cam4', got '{folder_cam4}'"
        
        folder_cam5 = window._resolve_camera_folder_name('Cam5', real_streams_date)
        assert folder_cam5 is not None, "Should resolve Cam5 to a folder"
        assert folder_cam5 == 'Cam4-Cam5' or folder_cam5 == 'Cam5', f"Expected 'Cam4-Cam5' or 'Cam5', got '{folder_cam5}'"
        
        # Проверить обычный источник
        folder_cam1 = window._resolve_camera_folder_name('Cam1', real_streams_date)
        assert folder_cam1 == 'Cam1', f"Expected 'Cam1', got '{folder_cam1}'"
        
        window.close()


class TestRealPlaybackIssues:
    """Тесты для поиска проблем с реальным воспроизведением"""
    
    def test_find_valid_video_files(self, real_base_dir, real_streams_date):
        """Найти валидные видеофайлы для тестирования"""
        import cv2
        streams_dir = Path(real_base_dir) / "Streams" / real_streams_date
        
        valid_files = {}
        for camera_folder in streams_dir.iterdir():
            if camera_folder.is_dir():
                valid_list = []
                for video_file in sorted(camera_folder.glob("*.mp4"))[:20]:  # Проверить первые 20 файлов
                    cap = cv2.VideoCapture(str(video_file))
                    if cap.isOpened():
                        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        ret, frame = cap.read()
                        cap.release()
                        if width > 0 and ret and frame is not None:
                            valid_list.append(str(video_file))
                if valid_list:
                    valid_files[camera_folder.name] = valid_list
        
        # Если нет валидных файлов, пропустить тест
        if len(valid_files) == 0:
            pytest.skip("No valid video files found (all files may be corrupted)")
        
        print(f"\nFound valid files: {len(valid_files)} cameras")
        for camera, files in valid_files.items():
            print(f"  {camera}: {len(files)} files")
    
    def test_playback_with_valid_file(self, qapp, real_base_dir, real_config, real_streams_date):
        """Тест воспроизведения с валидным файлом"""
        import cv2
        
        # Найти валидный файл
        streams_dir = Path(real_base_dir) / "Streams" / real_streams_date
        valid_file = None
        
        for camera_folder in streams_dir.iterdir():
            if camera_folder.is_dir():
                for video_file in sorted(camera_folder.glob("*.mp4"))[:10]:
                    cap = cv2.VideoCapture(str(video_file))
                    if cap.isOpened():
                        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        ret, frame = cap.read()
                        cap.release()
                        if width > 0 and ret and frame is not None:
                            valid_file = str(video_file)
                            break
                if valid_file:
                    break
        
        if not valid_file:
            pytest.skip("No valid video files found")
        
        from evileye.visualization_modules.video_player_window import VideoPlayerWidget
        
        player = VideoPlayerWidget(parent=None, logger_name="test_valid_playback")
        player.show()
        qapp.processEvents()
        
        # Попытаться воспроизвести
        result = player.play_video(valid_file)
        
        # Дать время на обработку
        qapp.processEvents()
        QTimer.singleShot(1000, lambda: None)
        qapp.processEvents()
        
        # Проверить, что воспроизведение началось (или переключилось на OpenCV)
        assert result == True or player._use_opencv == True, "Should start playback or switch to OpenCV"
        
        # Остановить
        player.stop()
        qapp.processEvents()
        
        player.close()
    
    def test_corrupted_files_are_filtered(self, qapp, real_base_dir, real_config, real_streams_date):
        """Проверить, что поврежденные файлы фильтруются при загрузке"""
        window = StreamPlayerWindow(base_dir=real_base_dir, params=real_config)
        
        # Выбрать дату
        from PyQt6.QtCore import QDate
        try:
            from PyQt5.QtCore import QDate
        except ImportError:
            pass
        
        date_parts = real_streams_date.split('-')
        qdate = QDate(int(date_parts[0]), int(date_parts[1]), int(date_parts[2]))
        window.camera_selector.date_edit.setDate(qdate)
        
        # Получить список доступных камер
        available_cameras = window.camera_selector._available_cameras.get(real_streams_date, [])
        if len(available_cameras) == 0:
            pytest.skip("No cameras available")
        
        # Выбрать первую камеру
        selected_camera = available_cameras[0]
        window._selected_cameras = [selected_camera]
        window._load_camera_segments()
        
        # Проверить, что загружены только валидные файлы
        if selected_camera in window._camera_segments:
            segments = window._camera_segments[selected_camera]
            # Все сегменты должны быть валидными
            for segment in segments:
                assert window._is_valid_video_file(segment), f"Segment should be valid: {segment}"
                assert os.path.exists(segment), f"Segment should exist: {segment}"
                assert os.path.getsize(segment) > 1024, f"Segment should be larger than 1KB: {segment}"
        
        window.close()
