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
        self._load_state()
        
    def _init_ui(self):
        """Инициализация интерфейса"""
        self.setWindowTitle("Stream Player")
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
        self.video_grid.grid_size_changed.connect(self.camera_selector.set_grid_size)
        main_layout.addWidget(self.video_grid, stretch=1)
        
        # Контролы воспроизведения
        self.playback_controls = PlaybackControlsWidget(self)
        self.playback_controls.play_clicked.connect(self._on_play_clicked)
        self.playback_controls.pause_clicked.connect(self._on_pause_clicked)
        self.playback_controls.stop_clicked.connect(self._on_stop_clicked)
        self.playback_controls.speed_changed.connect(self._on_speed_changed)
        main_layout.addWidget(self.playback_controls)
        
        # Опция показа метаданных
        try:
            from PyQt6.QtWidgets import QCheckBox
        except ImportError:
            from PyQt5.QtWidgets import QCheckBox
        
        metadata_layout = QHBoxLayout()
        self.show_metadata_checkbox = QCheckBox("Show metadata (objects and events)")
        self.show_metadata_checkbox.setChecked(False)
        self.show_metadata_checkbox.stateChanged.connect(self._on_metadata_toggled)
        metadata_layout.addWidget(self.show_metadata_checkbox)
        metadata_layout.addStretch()
        main_layout.addLayout(metadata_layout)
        
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
        date = self.camera_selector.get_selected_date() if hasattr(self.camera_selector, 'get_selected_date') else None
        self.video_grid.set_cameras(cameras, self._camera_segment_times, self._source_config, self.base_dir, date)
        self._configure_metadata_for_players()
        
    def _on_date_selected(self, date: str):
        """Обработка выбора даты"""
        self.logger.info(f"Selected date: {date}")
        self._load_events(date)
        self.timeline.set_events(self._events, self._event_filters)
        
        # Восстановить выбранные камеры если они были выбраны ранее
        if self._selected_cameras:
            self.logger.info(f"Restoring selected cameras: {self._selected_cameras}")
            self._load_camera_segments()
            self.video_grid.set_cameras(self._selected_cameras, self._camera_segment_times, self._source_config, self.base_dir, date)
            self._configure_metadata_for_players()
        else:
            self._configure_metadata_for_players()
        
    def _resolve_camera_folder_name(self, camera_name: str, date: str) -> Optional[str]:
        """
        Преобразовать имя источника в имя папки камеры.
        
        Args:
            camera_name: Имя источника (может быть отдельным источником или именем папки)
            date: Дата для проверки существования папки
            
        Returns:
            Имя папки камеры или None, если папка не найдена
        """
        streams_date_dir = os.path.join(self.streams_dir, date)
        if not os.path.exists(streams_date_dir):
            return None
        
        # Сначала проверить, существует ли папка с таким именем напрямую
        camera_dir = os.path.join(streams_date_dir, camera_name)
        if os.path.exists(camera_dir) and os.path.isdir(camera_dir):
            # Проверить наличие видео файлов
            video_files = glob.glob(os.path.join(camera_dir, '*.mp4'))
            if video_files:
                return camera_name
        
        # Если папка не найдена напрямую, попробовать найти через source_config
        source_config = self._source_config.get(camera_name)
        if source_config:
            # Если источник разделен и есть parent_folder, использовать его
            parent_folder = source_config.get('parent_folder')
            if parent_folder:
                parent_dir = os.path.join(streams_date_dir, parent_folder)
                if os.path.exists(parent_dir) and os.path.isdir(parent_dir):
                    video_files = glob.glob(os.path.join(parent_dir, '*.mp4'))
                    if video_files:
                        return parent_folder
            
            # Если источник разделен, попробовать составить имя папки из source_names
            if source_config.get('split', False):
                source_names = source_config.get('source_names', [])
                if source_names:
                    # Попробовать составное имя (например, "Cam2-Cam3")
                    composite_name = '-'.join(source_names)
                    composite_dir = os.path.join(streams_date_dir, composite_name)
                    if os.path.exists(composite_dir) and os.path.isdir(composite_dir):
                        video_files = glob.glob(os.path.join(composite_dir, '*.mp4'))
                        if video_files:
                            return composite_name
        
        # Попробовать найти папку, которая содержит это имя источника
        # (для случаев, когда папка называется составным именем)
        try:
            for item in os.listdir(streams_date_dir):
                item_path = os.path.join(streams_date_dir, item)
                if os.path.isdir(item_path):
                    # Проверить, содержит ли имя папки имя источника
                    if camera_name in item.split('-'):
                        video_files = glob.glob(os.path.join(item_path, '*.mp4'))
                        if video_files:
                            return item
        except OSError:
            pass
        
        return None
    
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
        
        # Маппинг исходных имен источников на имена папок
        camera_folder_mapping = {}
        
        for camera in self._selected_cameras:
            # Разрешить имя папки для источника
            folder_name = self._resolve_camera_folder_name(camera, date)
            
            if not folder_name:
                # Если папка не найдена, логировать на уровне DEBUG (ожидаемое поведение для отдельных источников)
                self.logger.debug(f"Camera folder not found for source '{camera}' in date {date}")
                continue
            
            camera_folder_mapping[camera] = folder_name
            
            camera_dir = os.path.join(streams_date_dir, folder_name)
            if not os.path.exists(camera_dir):
                self.logger.debug(f"Camera directory does not exist: {camera_dir}")
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
            
            if folder_name != camera:
                self.logger.info(f"Loaded {len(valid_segments)} valid segments (out of {len(all_segments)} total) for source '{camera}' from folder '{folder_name}'")
            else:
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
            # Собрать все сегменты записей для цветовой индикации
            recording_segments = []
            for camera_name, segments in self._camera_segment_times.items():
                for start_time_seg, end_time_seg, path in segments:
                    recording_segments.append((start_time_seg, end_time_seg))
            
            self.timeline.set_time_range(start_time, end_time, recording_segments)
            
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
        
        # Обновить визуальную индикацию кнопок
        self.playback_controls.set_state('playing')
        
    def _on_pause_clicked(self):
        """Обработка нажатия Pause"""
        self._is_playing = False
        self.video_grid.pause_all()
        self._sync_timer.stop()
        
        # Обновить визуальную индикацию кнопок
        self.playback_controls.set_state('paused')
        
    def _on_stop_clicked(self):
        """Обработка нажатия Stop"""
        self._is_playing = False
        self._current_position_ms = 0
        self.video_grid.stop_all()
        self._sync_timer.stop()
        self.timeline.set_position(0)
        
        # Обновить визуальную индикацию кнопок
        self.playback_controls.set_state('idle')
        
    def _on_speed_changed(self, speed: float):
        """Обработка изменения скорости воспроизведения"""
        self._playback_speed = speed
        self.video_grid.set_playback_speed(speed)
        self.save_state()  # Сохранить состояние при изменении скорости
        
    def _on_timeline_position_changed(self, position_ms: int):
        """Обработка изменения позиции на временной шкале"""
        self._current_position_ms = position_ms
        # Передать состояние воспроизведения в seek_all, чтобы восстановить воспроизведение после перезагрузки видео
        self.video_grid.seek_all(position_ms, should_play=self._is_playing)
        
    def _on_video_position_changed(self, position_ms: int):
        """Обработка изменения позиции в видео"""
        self._current_position_ms = position_ms
        self.timeline.set_position(position_ms)
        
    def _on_event_filters_changed(self, filters: Dict[str, bool]):
        """Обработка изменения фильтров событий"""
        self._event_filters = filters
        self.timeline.set_events(self._events, filters)
        self.save_state()  # Сохранить состояние при изменении фильтров
    
    def _on_metadata_toggled(self, state):
        """Обработка переключения показа метаданных"""
        try:
            from PyQt6.QtCore import Qt
        except ImportError:
            from PyQt5.QtCore import Qt
        
        show_metadata = state == Qt.CheckState.Checked.value if hasattr(Qt.CheckState, 'Checked') else state == 2
        self._update_metadata_visibility(show_metadata)
        self.save_state()
    
    def _configure_metadata_for_players(self):
        """Настроить метаданные для всех видеоплееров"""
        date = self.camera_selector.get_selected_date() if hasattr(self.camera_selector, 'get_selected_date') else None
        if not date:
            return
        
        for camera_name, player in self.video_grid._video_players.items():
            if hasattr(player, 'set_metadata_config'):
                # Определить имя источника
                source_name = camera_name
                split_config = self._source_config.get(camera_name)
                if split_config and split_config.get('split', False):
                    # Для разделенных потоков используем первое имя источника
                    source_names = split_config.get('source_names', [])
                    if source_names:
                        source_name = source_names[0]
                
                player.set_metadata_config(self.base_dir, date, source_name)
    
    def _update_metadata_visibility(self, show: bool):
        """Обновить видимость метаданных для всех плееров"""
        for player in self.video_grid._video_players.values():
            if hasattr(player, 'set_show_metadata'):
                player.set_show_metadata(show)
    
    def _update_metadata_for_time(self, timestamp: datetime.datetime):
        """Обновить метаданные для всех плееров для указанного времени"""
        for player in self.video_grid._video_players.values():
            if hasattr(player, 'update_metadata_for_time'):
                player.update_metadata_for_time(timestamp)
    
    def _find_next_available_time(self, target_time: datetime.datetime) -> Optional[datetime.datetime]:
        """Найти следующий момент времени, где есть записи для всех камер"""
        if not self._camera_segment_times:
            return None
        
        next_times = []
        
        # Для каждой камеры найти следующий сегмент после target_time
        for camera, segments in self._camera_segment_times.items():
            if not segments:
                continue
            
            # segments может быть списком кортежей (start_time, end_time, path)
            for start_time, end_time, path in segments:
                if start_time and start_time > target_time:
                    next_times.append(start_time)
                    break
        
        if not next_times:
            # Все сегменты закончились
            return None
        
        # Вернуть минимальное время начала следующего сегмента
        return min(next_times)
    
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
        
        # Проверить, есть ли записи для текущего момента времени
        if self._start_time:
            current_time = self._start_time + datetime.timedelta(milliseconds=self._current_position_ms)
            
            # Проверить, есть ли хотя бы одна запись для текущего времени
            has_recording = False
            for camera, segments in self._camera_segment_times.items():
                if not segments:
                    continue
                for start_time, end_time, path in segments:
                    if start_time and end_time and start_time <= current_time < end_time:
                        has_recording = True
                        break
                if has_recording:
                    break
            
            # Если нет записи, найти следующий доступный момент
            if not has_recording:
                next_time = self._find_next_available_time(current_time)
                if next_time:
                    # Вычислить новую позицию в миллисекундах
                    time_diff = (next_time - self._start_time).total_seconds()
                    new_position_ms = int(time_diff * 1000)
                    # Вызвать seek_all только если позиция действительно изменилась значительно
                    if abs(new_position_ms - self._current_position_ms) > 1000:  # Разница больше 1 секунды
                        self._current_position_ms = new_position_ms
                        self.logger.debug(f"Jumped to next available time: {next_time}, position_ms={self._current_position_ms}")
                        # Вызвать seek_all для перемотки на новую позицию
                        self.video_grid.seek_all(self._current_position_ms, should_play=self._is_playing)
                else:
                    # Нет больше записей, остановить воспроизведение
                    self._current_position_ms = self._total_duration_ms
                    self._on_stop_clicked()
                    return
        
        # Обновить позицию на timeline (без вызова seek_all, чтобы избежать постоянной перемотки)
        # seek_all вызывается только при явной перемотке пользователем или при начальной загрузке
        self.timeline.set_position(self._current_position_ms)
        
        # Обновить метаданные для текущего времени
        if self._start_time and hasattr(self, 'show_metadata_checkbox') and self.show_metadata_checkbox.isChecked():
            current_time = self._start_time + datetime.timedelta(milliseconds=self._current_position_ms)
            self._update_metadata_for_time(current_time)
        
    def save_state(self):
        """Сохранить состояние плеера в params"""
        if not self.params:
            return
        
        # Создать секцию stream_player если её нет
        if 'stream_player' not in self.params:
            self.params['stream_player'] = {}
        
        state = {
            'selected_cameras': self._selected_cameras.copy(),
            'playback_speed': self._playback_speed,
            'event_filters': self._event_filters.copy(),
            'grid_rows': getattr(self.camera_selector, 'rows_spin', None) and self.camera_selector.rows_spin.value() or 2,
            'grid_cols': getattr(self.camera_selector, 'cols_spin', None) and self.camera_selector.cols_spin.value() or 2,
            'last_date': self.camera_selector.get_selected_date() if hasattr(self.camera_selector, 'get_selected_date') else None,
            'grid_cell_sources': getattr(self.video_grid, '_grid_cell_sources', {}).copy(),
            'show_metadata': getattr(self, 'show_metadata_checkbox', None) and self.show_metadata_checkbox.isChecked() or False
        }
        
        self.params['stream_player'] = state
        self.logger.debug("Player state saved to params")
    
    def _load_state(self):
        """Загрузить состояние плеера из params"""
        if not self.params or 'stream_player' not in self.params:
            return
        
        state = self.params.get('stream_player', {})
        
        # Восстановить фильтры событий
        if 'event_filters' in state:
            self._event_filters.update(state['event_filters'])
            # Применить фильтры к timeline
            if hasattr(self, 'timeline'):
                self.timeline.set_events(self._events, self._event_filters)
        
        # Восстановить скорость воспроизведения
        if 'playback_speed' in state:
            self._playback_speed = state['playback_speed']
            if hasattr(self, 'playback_controls'):
                self.playback_controls.set_speed(self._playback_speed)
        
        # Восстановить размеры сетки
        if 'grid_rows' in state and hasattr(self.camera_selector, 'rows_spin'):
            self.camera_selector.rows_spin.setValue(state['grid_rows'])
        if 'grid_cols' in state and hasattr(self.camera_selector, 'cols_spin'):
            self.camera_selector.cols_spin.setValue(state['grid_cols'])
        
        # Восстановить выбранные камеры (до восстановления даты, чтобы они были доступны при смене даты)
        if 'selected_cameras' in state and state['selected_cameras']:
            self._selected_cameras = state['selected_cameras'].copy()
        
        # Восстановить последнюю выбранную дату
        if 'last_date' in state and state['last_date']:
            try:
                date_parts = state['last_date'].split('-')
                if len(date_parts) == 3:
                    from PyQt6.QtCore import QDate
                    try:
                        from PyQt5.QtCore import QDate
                    except ImportError:
                        pass
                    qdate = QDate(int(date_parts[0]), int(date_parts[1]), int(date_parts[2]))
                    self.camera_selector.date_edit.setDate(qdate)
                    # После установки даты автоматически восстановятся камеры через _on_date_selected
            except Exception as e:
                self.logger.debug(f"Failed to restore date: {e}")
        
        # Восстановить состояние показа метаданных
        if 'show_metadata' in state and hasattr(self, 'show_metadata_checkbox'):
            self.show_metadata_checkbox.setChecked(state['show_metadata'])
            self._update_metadata_visibility(state['show_metadata'])
        
        self.logger.debug("Player state loaded from params")
    
    def closeEvent(self, event):
        """Обработка закрытия окна"""
        self._on_stop_clicked()
        self.save_state()
        super().closeEvent(event)
