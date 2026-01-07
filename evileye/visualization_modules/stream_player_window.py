"""
Окно плеера потоковых записей
Поддерживает воспроизведение сетки видео NxM с синхронизацией
"""

import os
import sys
import datetime
import glob
from pathlib import Path
from typing import Optional, List, Dict, Tuple

try:
    from PyQt6.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QPushButton, QSlider, QCheckBox, QComboBox, QSpinBox,
        QGroupBox, QScrollArea, QMessageBox, QFileDialog
    )
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QUrl
    from PyQt6.QtGui import QIcon
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QPushButton, QSlider, QCheckBox, QComboBox, QSpinBox,
        QGroupBox, QScrollArea, QMessageBox, QFileDialog
    )
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QUrl
    from PyQt5.QtGui import QIcon
    pyqt_version = 5

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from ..core.logger import get_module_logger
from .stream_player_components import (
    CameraSelectorWidget, VideoGridWidget, TimelineWidget, PlaybackControlsWidget
)
import logging


class StreamPlayerWindow(QMainWindow):
    """Окно плеера потоковых записей с поддержкой сетки видео NxM"""
    
    def __init__(self, base_dir: str = None, params: Dict = None, parent=None):
        super().__init__(parent)
        self.logger = get_module_logger("stream_player_window")
        
        self.base_dir = base_dir or 'EvilEyeData'
        self.streams_dir = os.path.join(self.base_dir, 'Streams')
        self.events_dir = os.path.join(self.base_dir, 'Events')
        self.params = params or {}
        
        # Конфигурация источников для разделения потоков
        self._source_config = {}  # {camera_folder: {split, num_split, src_coords, source_names, source_ids}}
        self._load_source_config()
        
        # Состояние воспроизведения
        self._is_playing = False
        self._playback_speed = 1.0
        self._current_position_ms = 0
        self._total_duration_ms = 0
        self._start_time = None  # datetime начала воспроизведения
        self._time_range = None  # (start_datetime, end_datetime)
        
        # Выбранные камеры и их сегменты
        self._selected_cameras = []
        self._camera_segments = {}  # {camera_name: [list of segment paths]}
        self._camera_segment_times = {}  # {camera_name: [(start_time, end_time, path)]}
        
        # События для меток
        self._events = []
        self._event_filters = {
            'camera_events': True,
            'system_events': True,
            'zone_events_entered': True,
            'zone_events_left': True
        }
        
        # Таймер для синхронизации
        self._sync_timer = QTimer()
        self._sync_timer.timeout.connect(self._sync_playback)
        
        self._init_ui()
        
    def _init_ui(self):
        """Инициализация интерфейса"""
        self.setWindowTitle("Stream Player - Плеер потоковых записей")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)
        
        # Центрирование окна
        if self.parent():
            parent_geometry = self.parent().geometry()
            self.move(
                parent_geometry.x() + (parent_geometry.width() - 1400) // 2,
                parent_geometry.y() + (parent_geometry.height() - 900) // 2
            )
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Главный layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(5)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        # Селектор камер (вверху)
        self.camera_selector = CameraSelectorWidget(self.base_dir, self, self._source_config)
        self.camera_selector.cameras_selected.connect(self._on_cameras_selected)
        self.camera_selector.date_selected.connect(self._on_date_selected)
        main_layout.addWidget(self.camera_selector)
        
        # Сетка видео (в центре)
        self.video_grid = VideoGridWidget(self)
        self.video_grid.position_changed.connect(self._on_video_position_changed)
        main_layout.addWidget(self.video_grid, stretch=1)
        
        # Контролы воспроизведения
        self.playback_controls = PlaybackControlsWidget(self)
        self.playback_controls.play_clicked.connect(self._on_play_clicked)
        self.playback_controls.pause_clicked.connect(self._on_pause_clicked)
        self.playback_controls.stop_clicked.connect(self._on_stop_clicked)
        self.playback_controls.speed_changed.connect(self._on_speed_changed)
        main_layout.addWidget(self.playback_controls)
        
        # Временная шкала (внизу)
        self.timeline = TimelineWidget(self)
        self.timeline.position_changed.connect(self._on_timeline_position_changed)
        self.timeline.filters_changed.connect(self._on_event_filters_changed)
        main_layout.addWidget(self.timeline)
        
    def _on_cameras_selected(self, cameras: List[str]):
        """Обработка выбора камер"""
        self._selected_cameras = cameras
        self.logger.info(f"Selected cameras: {cameras}")
        self._load_camera_segments()
        self.video_grid.set_cameras(cameras, self._camera_segment_times, self._source_config)
        
    def _on_date_selected(self, date: str):
        """Обработка выбора даты"""
        self.logger.info(f"Selected date: {date}")
        self._load_events(date)
        self.timeline.set_events(self._events, self._event_filters)
        
    def _load_camera_segments(self):
        """Загрузка сегментов видео для выбранных камер"""
        if not self._selected_cameras:
            return
            
        date = self.camera_selector.get_selected_date()
        if not date:
            return
            
        self._camera_segments = {}
        self._camera_segment_times = {}
        
        streams_date_dir = os.path.join(self.streams_dir, date)
        if not os.path.exists(streams_date_dir):
            self.logger.warning(f"Streams directory does not exist: {streams_date_dir}")
            return
        
        for camera in self._selected_cameras:
            camera_dir = os.path.join(streams_date_dir, camera)
            if not os.path.exists(camera_dir):
                self.logger.warning(f"Camera directory does not exist: {camera_dir}")
                continue
                
            # Найти все сегменты видео и проверить их валидность
            all_segments = sorted(glob.glob(os.path.join(camera_dir, '*.mp4')))
            valid_segments = []
            
            for segment_path in all_segments:
                # Проверить валидность файла перед добавлением
                if self._is_valid_video_file(segment_path):
                    valid_segments.append(segment_path)
                else:
                    self.logger.debug(f"Skipping invalid/corrupted video file: {segment_path}")
            
            self._camera_segments[camera] = valid_segments
            
            # Определить временные диапазоны сегментов
            segment_times = []
            for segment_path in valid_segments:
                start_time, duration = self._get_segment_time_info(segment_path)
                if start_time:
                    end_time = start_time + datetime.timedelta(seconds=duration)
                    segment_times.append((start_time, end_time, segment_path))
            
            self._camera_segment_times[camera] = sorted(segment_times, key=lambda x: x[0])
            
            self.logger.info(f"Loaded {len(valid_segments)} valid segments (out of {len(all_segments)} total) for camera {camera}")
        
        # Определить общий временной диапазон
        self._calculate_time_range()
    
    def _load_source_config(self):
        """Загрузить конфигурацию источников из params для определения разделенных потоков"""
        self._source_config = {}
        
        if not self.params:
            self.logger.debug("No params provided, skipping source config loading")
            return
        
        pipeline_sources = self.params.get('pipeline', {}).get('sources', [])
        if not pipeline_sources:
            self.logger.debug("No pipeline sources found in params")
            return
        
        # Создать маппинг: имя папки камеры → параметры разделения
        for source_config in pipeline_sources:
            if not isinstance(source_config, dict):
                continue
            
            source_names = source_config.get('source_names', [])
            split = source_config.get('split', False)
            num_split = source_config.get('num_split', 0)
            src_coords = source_config.get('src_coords', [])
            source_ids = source_config.get('source_ids', [])
            
            if not source_names:
                continue
            
            # Определить имя папки камеры
            # Если split=True и несколько source_names, имя папки может быть составным (например, "Cam2-Cam3")
            # Или может быть одно имя для всех источников
            if split and num_split > 1 and len(source_names) >= num_split:
                # Попробовать найти папку по составному имени
                camera_folder = '-'.join(source_names[:num_split])
                # Также добавить маппинг для каждого отдельного имени
                for i, source_name in enumerate(source_names[:num_split]):
                    if source_name not in self._source_config:
                        self._source_config[source_name] = {
                            'split': True,
                            'num_split': 1,
                            'src_coords': [src_coords[i]] if i < len(src_coords) else [],
                            'source_names': [source_name],
                            'source_ids': [source_ids[i]] if i < len(source_ids) else [],
                            'parent_folder': camera_folder,
                            'split_index': i
                        }
                
                # Добавить конфигурацию для составной папки
                self._source_config[camera_folder] = {
                    'split': True,
                    'num_split': num_split,
                    'src_coords': src_coords[:num_split] if len(src_coords) >= num_split else [],
                    'source_names': source_names[:num_split],
                    'source_ids': source_ids[:num_split] if len(source_ids) >= num_split else []
                }
            else:
                # Обычный источник без разделения
                camera_folder = source_names[0] if source_names else None
                if camera_folder:
                    self._source_config[camera_folder] = {
                        'split': False,
                        'num_split': 1,
                        'src_coords': [],
                        'source_names': source_names[:1],
                        'source_ids': source_ids[:1] if source_ids else []
                    }
        
        self.logger.info(f"Loaded source config for {len(self._source_config)} camera folders")
    
    def _get_split_config(self, camera_folder: str) -> Optional[Dict]:
        """Получить параметры разделения для папки камеры"""
        return self._source_config.get(camera_folder)
        
    def _get_segment_time_info(self, segment_path: str) -> Tuple[Optional[datetime.datetime], float]:
        """Получить время начала и длительность сегмента из имени файла"""
        filename = os.path.basename(segment_path)
        # Формат: Cam2_20260105_091017_0_00000.mp4
        parts = filename.replace('.mp4', '').split('_')
        
        if len(parts) >= 3:
            try:
                date_part = parts[1]  # YYYYMMDD
                time_part = parts[2]  # HHMMSS
                time_str = f"{date_part}_{time_part}"
                start_time = datetime.datetime.strptime(time_str, '%Y%m%d_%H%M%S')
                
                # Получить длительность из видео файла
                duration = self._get_video_duration(segment_path)
                return start_time, duration
            except Exception as e:
                self.logger.debug(f"Error parsing segment filename '{filename}': {e}")
        
        return None, 0.0
    
    def _is_valid_video_file(self, video_path: str) -> bool:
        """Проверить валидность видеофайла перед загрузкой"""
        if not video_path or not os.path.exists(video_path):
            return False
        
        # Проверить размер файла (должен быть больше 1KB)
        try:
            file_size = os.path.getsize(video_path)
            if file_size < 1024:  # Меньше 1KB - вероятно пустой или поврежденный
                return False
        except Exception:
            return False
        
        # Проверить возможность открытия через OpenCV (быстрая проверка)
        try:
            import cv2
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                cap.release()
                return False
            
            # Попытаться прочитать первый кадр
            ret, frame = cap.read()
            cap.release()
            
            if not ret or frame is None:
                return False
            
            # Дополнительная проверка: попытаться получить метаданные
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.release()
            
            # Если fps и frame_count равны 0, файл может быть поврежден
            if fps == 0 and frame_count == 0:
                return False
            
            return True
        except Exception as e:
            self.logger.debug(f"Error validating video file {video_path}: {e}")
            return False
    
    def _get_video_duration(self, video_path: str) -> float:
        """Получить длительность видео файла"""
        try:
            import cv2
            cap = cv2.VideoCapture(video_path)
            if cap.isOpened():
                fps = cap.get(cv2.CAP_PROP_FPS) or 30
                frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                duration = frame_count / fps if fps > 0 else 0
                cap.release()
                if duration > 0:
                    return duration
        except Exception as e:
            self.logger.debug(f"Error getting video duration: {e}")
        
        # Fallback: предполагаем 5 минут (300 секунд)
        return 300.0
    
    def _calculate_time_range(self):
        """Вычислить общий временной диапазон всех записей"""
        if not self._camera_segment_times:
            self._time_range = None
            return
        
        all_start_times = []
        all_end_times = []
        
        for camera, segments in self._camera_segment_times.items():
            if segments:
                all_start_times.append(segments[0][0])
                all_end_times.append(segments[-1][1])
        
        if all_start_times and all_end_times:
            start_time = min(all_start_times)
            end_time = max(all_end_times)
            self._time_range = (start_time, end_time)
            self._start_time = start_time
            
            # Обновить временную шкалу
            total_seconds = (end_time - start_time).total_seconds()
            self._total_duration_ms = int(total_seconds * 1000)
            self.timeline.set_time_range(start_time, end_time)
            
            self.logger.info(f"Time range: {start_time} to {end_time}")
    
    def _load_events(self, date: str):
        """Загрузка событий из JSON файлов"""
        self._events = []
        
        events_date_dir = os.path.join(self.events_dir, date, 'Metadata')
        if not os.path.exists(events_date_dir):
            self.logger.debug(f"Events directory does not exist: {events_date_dir}")
            return
        
        event_files = {
            'camera_events': 'camera_events.json',
            'system_events': 'system_events.json',
            'zone_events_entered': 'zone_events_entered.json',
            'zone_events_left': 'zone_events_left.json'
        }
        
        for event_type, filename in event_files.items():
            filepath = os.path.join(events_date_dir, filename)
            if os.path.exists(filepath):
                try:
                    import json
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    if isinstance(data, list):
                        for event in data:
                            event['event_type'] = event_type
                            self._events.append(event)
                    elif isinstance(data, dict) and 'events' in data:
                        for event in data['events']:
                            event['event_type'] = event_type
                            self._events.append(event)
                            
                except Exception as e:
                    self.logger.warning(f"Error loading events from {filepath}: {e}")
        
        self.logger.info(f"Loaded {len(self._events)} events")
        self.timeline.set_events(self._events, self._event_filters)
    
    def _on_play_clicked(self):
        """Обработка нажатия Play"""
        if not self._selected_cameras:
            QMessageBox.warning(self, "No cameras selected", "Please select at least one camera")
            return
        
        self._is_playing = True
        self.video_grid.play_all()
        
        # Запустить таймер синхронизации (обновление каждые 100мс)
        self._sync_timer.start(100)
        
    def _on_pause_clicked(self):
        """Обработка нажатия Pause"""
        self._is_playing = False
        self.video_grid.pause_all()
        self._sync_timer.stop()
        
    def _on_stop_clicked(self):
        """Обработка нажатия Stop"""
        self._is_playing = False
        self._current_position_ms = 0
        self.video_grid.stop_all()
        self._sync_timer.stop()
        self.timeline.set_position(0)
        
    def _on_speed_changed(self, speed: float):
        """Обработка изменения скорости воспроизведения"""
        self._playback_speed = speed
        self.video_grid.set_playback_speed(speed)
        
    def _on_timeline_position_changed(self, position_ms: int):
        """Обработка изменения позиции на временной шкале"""
        self._current_position_ms = position_ms
        self.video_grid.seek_all(position_ms)
        
    def _on_video_position_changed(self, position_ms: int):
        """Обработка изменения позиции в видео"""
        self._current_position_ms = position_ms
        self.timeline.set_position(position_ms)
        
    def _on_event_filters_changed(self, filters: Dict[str, bool]):
        """Обработка изменения фильтров событий"""
        self._event_filters = filters
        self.timeline.set_events(self._events, filters)
        
    def _sync_playback(self):
        """Синхронизация воспроизведения всех видео"""
        if not self._is_playing:
            return
        
        # Обновить позицию с учетом скорости (таймер вызывается каждые 100мс)
        self._current_position_ms += int(100 * self._playback_speed)
        
        if self._current_position_ms >= self._total_duration_ms:
            self._current_position_ms = self._total_duration_ms
            self._on_stop_clicked()
            return
        
        # Синхронизировать все видео (только если позиция изменилась значительно)
        # Избегаем частых обновлений для производительности
        if self._current_position_ms % 100 == 0:  # Обновлять каждые 100мс
            self.video_grid.seek_all(self._current_position_ms)
            self.timeline.set_position(self._current_position_ms)
        
    def closeEvent(self, event):
        """Обработка закрытия окна"""
        self._on_stop_clicked()
        super().closeEvent(event)
