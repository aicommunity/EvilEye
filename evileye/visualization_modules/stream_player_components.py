"""
Компоненты плеера потоковых записей
"""

import os
import sys
import datetime
import glob
from pathlib import Path
from typing import Optional, List, Dict, Tuple

try:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QPushButton, QSlider, QCheckBox, QComboBox, QSpinBox,
        QGroupBox, QScrollArea, QButtonGroup, QDateEdit
    )
    from PyQt6.QtCore import Qt, pyqtSignal, QDate
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QPushButton, QSlider, QCheckBox, QComboBox, QSpinBox,
        QGroupBox, QScrollArea, QButtonGroup, QDateEdit
    )
    from PyQt5.QtCore import Qt, pyqtSignal, QDate
    pyqt_version = 5

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from ..core.logger import get_module_logger
from .video_player_window import VideoPlayerWidget
import logging


class CameraSelectorWidget(QWidget):
    """Виджет для выбора камер и даты"""
    
    cameras_selected = pyqtSignal(list)
    date_selected = pyqtSignal(str)
    
    def __init__(self, base_dir: str, parent=None):
        super().__init__(parent)
        self.logger = get_module_logger("camera_selector")
        self.base_dir = base_dir
        self.streams_dir = os.path.join(base_dir, 'Streams')
        
        self._available_dates = []
        self._available_cameras = {}
        self._selected_cameras = []
        
        self._init_ui()
        self._load_available_dates()
        
    def _init_ui(self):
        """Инициализация интерфейса"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Группа выбора даты
        date_group = QGroupBox("Дата")
        date_layout = QVBoxLayout()
        
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.dateChanged.connect(self._on_date_changed)
        date_layout.addWidget(self.date_edit)
        
        date_group.setLayout(date_layout)
        layout.addWidget(date_group)
        
        # Группа выбора камер
        cameras_group = QGroupBox("Камеры")
        cameras_layout = QVBoxLayout()
        
        # Scroll area для списка камер
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(150)
        
        self.cameras_widget = QWidget()
        self.cameras_layout = QVBoxLayout(self.cameras_widget)
        self.cameras_layout.setContentsMargins(5, 5, 5, 5)
        
        self.camera_checkboxes = {}
        self.camera_group = QButtonGroup()
        self.camera_group.setExclusive(False)
        
        scroll.setWidget(self.cameras_widget)
        cameras_layout.addWidget(scroll)
        
        # Кнопки управления
        buttons_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("Выбрать все")
        self.select_all_btn.clicked.connect(self._select_all)
        self.deselect_all_btn = QPushButton("Снять все")
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        buttons_layout.addWidget(self.select_all_btn)
        buttons_layout.addWidget(self.deselect_all_btn)
        cameras_layout.addLayout(buttons_layout)
        
        cameras_group.setLayout(cameras_layout)
        layout.addWidget(cameras_group, stretch=1)
        
        # Группа настроек сетки
        grid_group = QGroupBox("Сетка видео")
        grid_layout = QHBoxLayout()
        
        grid_layout.addWidget(QLabel("Строк:"))
        self.rows_spin = QSpinBox()
        self.rows_spin.setMinimum(1)
        self.rows_spin.setMaximum(4)
        self.rows_spin.setValue(2)
        grid_layout.addWidget(self.rows_spin)
        
        grid_layout.addWidget(QLabel("Столбцов:"))
        self.cols_spin = QSpinBox()
        self.cols_spin.setMinimum(1)
        self.cols_spin.setMaximum(4)
        self.cols_spin.setValue(2)
        grid_layout.addWidget(self.cols_spin)
        
        grid_group.setLayout(grid_layout)
        layout.addWidget(grid_group)
        
    def _load_available_dates(self):
        """Загрузка доступных дат из папки Streams"""
        if not os.path.exists(self.streams_dir):
            self.logger.warning(f"Streams directory does not exist: {self.streams_dir}")
            return
        
        dates = []
        for item in os.listdir(self.streams_dir):
            item_path = os.path.join(self.streams_dir, item)
            if os.path.isdir(item_path):
                try:
                    # Проверить формат даты YYYY-MM-DD
                    datetime.datetime.strptime(item, '%Y-%m-%d')
                    dates.append(item)
                except ValueError:
                    continue
        
        self._available_dates = sorted(dates, reverse=True)
        
        if self._available_dates:
            # Установить последнюю доступную дату
            latest_date = self._available_dates[0]
            date_parts = latest_date.split('-')
            self.date_edit.setDate(QDate(int(date_parts[0]), int(date_parts[1]), int(date_parts[2])))
            self._on_date_changed()
        
    def _on_date_changed(self):
        """Обработка изменения даты"""
        date = self.date_edit.date()
        date_str = date.toString('yyyy-MM-dd')
        self._load_cameras_for_date(date_str)
        self.date_selected.emit(date_str)
        
    def _load_cameras_for_date(self, date: str):
        """Загрузка доступных камер для указанной даты"""
        date_dir = os.path.join(self.streams_dir, date)
        if not os.path.exists(date_dir):
            self.logger.warning(f"Date directory does not exist: {date_dir}")
            return
        
        # Очистить существующие чекбоксы
        for checkbox in self.camera_checkboxes.values():
            self.cameras_layout.removeWidget(checkbox)
            checkbox.deleteLater()
        self.camera_checkboxes.clear()
        
        # Найти все папки камер
        cameras = []
        for item in os.listdir(date_dir):
            item_path = os.path.join(date_dir, item)
            if os.path.isdir(item_path):
                # Проверить наличие видео файлов
                video_files = glob.glob(os.path.join(item_path, '*.mp4'))
                if video_files:
                    cameras.append(item)
        
        self._available_cameras[date] = sorted(cameras)
        
        # Создать чекбоксы для камер
        for camera in self._available_cameras[date]:
            checkbox = QCheckBox(camera)
            checkbox.stateChanged.connect(self._on_camera_selection_changed)
            self.camera_checkboxes[camera] = checkbox
            self.cameras_layout.addWidget(checkbox)
        
        self.logger.info(f"Loaded {len(cameras)} cameras for date {date}")
        
    def _on_camera_selection_changed(self):
        """Обработка изменения выбора камер"""
        selected = []
        for camera, checkbox in self.camera_checkboxes.items():
            if checkbox.isChecked():
                selected.append(camera)
        
        self._selected_cameras = selected
        self.cameras_selected.emit(selected)
        
    def _select_all(self):
        """Выбрать все камеры"""
        for checkbox in self.camera_checkboxes.values():
            checkbox.setChecked(True)
        
    def _deselect_all(self):
        """Снять выбор со всех камер"""
        for checkbox in self.camera_checkboxes.values():
            checkbox.setChecked(False)
    
    def get_selected_date(self) -> str:
        """Получить выбранную дату"""
        date = self.date_edit.date()
        return date.toString('yyyy-MM-dd')
    
    def get_grid_size(self) -> Tuple[int, int]:
        """Получить размер сетки"""
        return (self.rows_spin.value(), self.cols_spin.value())


class VideoGridWidget(QWidget):
    """Виджет сетки видео NxM"""
    
    position_changed = pyqtSignal(int)  # position in milliseconds
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_module_logger("video_grid")
        
        self._cameras = []
        self._camera_segments = {}  # {camera: [(start_time, end_time, path)]}
        self._video_players = {}  # {camera_name: VideoPlayerWidget}
        self._current_segments = {}  # {camera_name: current_segment_path}
        self._current_segment_indices = {}  # {camera_name: index in segments list}
        self._playback_speed = 1.0
        self._start_time = None  # datetime начала общего временного диапазона
        
        self._init_ui()
        
    def _init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(2)
        
        container = QWidget()
        container.setLayout(self.grid_layout)
        layout.addWidget(container)
        
    def set_cameras(self, cameras: List[str], camera_segments: Dict[str, List[Tuple]]):
        """Установить камеры и их сегменты"""
        self._cameras = cameras
        self._camera_segments = camera_segments
        
        # Очистить существующие виджеты
        self._clear_grid()
        
        if not cameras:
            return
        
        # Определить размер сетки
        rows = 2
        cols = 2
        if len(cameras) == 1:
            rows, cols = 1, 1
        elif len(cameras) <= 2:
            rows, cols = 1, 2
        elif len(cameras) <= 4:
            rows, cols = 2, 2
        elif len(cameras) <= 6:
            rows, cols = 2, 3
        else:
            rows, cols = 3, 3
        
        # Определить общее время начала
        if camera_segments:
            all_starts = []
            for segments in camera_segments.values():
                if segments:
                    all_starts.append(segments[0][0])
            if all_starts:
                self._start_time = min(all_starts)
        
        # Создать виджеты видео для каждой камеры
        for idx, camera in enumerate(cameras[:rows * cols]):
            row = idx // cols
            col = idx % cols
            
            # Создать контейнер для видео и метки
            container_widget = QWidget()
            container_layout = QVBoxLayout(container_widget)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.setSpacing(0)
            
            # Метка с именем камеры
            label = QLabel(camera)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("background-color: rgba(0, 0, 0, 200); color: white; padding: 3px; font-weight: bold;")
            container_layout.addWidget(label)
            
            # Создать виджет видео
            video_widget = VideoPlayerWidget(parent=container_widget, logger_name=f"camera_{camera}")
            self._video_players[camera] = video_widget
            container_layout.addWidget(video_widget, stretch=1)
            
            # Загрузить первый сегмент
            if camera in camera_segments and camera_segments[camera]:
                first_segment = camera_segments[camera][0][2]  # (start, end, path)
                # Преобразовать в абсолютный путь если нужно
                if not os.path.isabs(first_segment):
                    first_segment = os.path.abspath(first_segment)
                
                if os.path.exists(first_segment) and os.path.getsize(first_segment) > 1024:
                    if video_widget.play_video(first_segment):
                        self._current_segments[camera] = first_segment
                        self._current_segment_indices[camera] = 0
                    else:
                        self.logger.warning(f"Failed to play video for camera {camera}: {first_segment}")
                else:
                    self.logger.warning(f"Video file not found or too small for camera {camera}: {first_segment}")
            
            # Добавить контейнер в сетку
            self.grid_layout.addWidget(container_widget, row, col)
        
    def _clear_grid(self):
        """Очистить сетку"""
        for camera, player in self._video_players.items():
            player.stop()
            player.deleteLater()
        self._video_players.clear()
        self._current_segments.clear()
        self._current_segment_indices.clear()
        
        # Удалить все виджеты из layout
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def play_all(self):
        """Запустить воспроизведение всех видео"""
        for player in self._video_players.values():
            # Видео уже загружено, нужно только возобновить воспроизведение
            # VideoPlayerWidget автоматически начинает воспроизведение при загрузке
            if hasattr(player, 'player') and player.player:
                if pyqt_version == 6:
                    player.player.play()
                else:
                    player.player.play()
            elif hasattr(player, 'timer') and player.timer:
                if not player.timer.isActive():
                    player.timer.start()
    
    def pause_all(self):
        """Приостановить воспроизведение всех видео"""
        for player in self._video_players.values():
            if hasattr(player, 'player') and player.player:
                try:
                    if pyqt_version == 6:
                        from PyQt6.QtMultimedia import QMediaPlayer
                        if player.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                            player.player.pause()
                    else:
                        from PyQt5.QtMultimedia import QMediaPlayer
                        if player.player.state() == QMediaPlayer.PlayingState:
                            player.player.pause()
                except Exception:
                    pass
            elif hasattr(player, 'timer') and player.timer:
                if player.timer.isActive():
                    player.timer.stop()
    
    def stop_all(self):
        """Остановить воспроизведение всех видео"""
        for player in self._video_players.values():
            player.stop()
    
    def seek_all(self, position_ms: int):
        """Перемотать все видео на указанную позицию"""
        if self._start_time is None:
            return
        
        # Вычислить абсолютное время
        target_time = self._start_time + datetime.timedelta(milliseconds=position_ms)
        
        for camera in self._cameras:
            if camera not in self._camera_segments:
                continue
                
            segments = self._camera_segments[camera]
            if not segments:
                continue
            
            # Найти нужный сегмент
            target_segment_idx = None
            for idx, (start_time, end_time, path) in enumerate(segments):
                if start_time <= target_time < end_time:
                    target_segment_idx = idx
                    break
            
            if target_segment_idx is None:
                # Вне диапазона, использовать ближайший
                if target_time < segments[0][0]:
                    target_segment_idx = 0
                elif target_time >= segments[-1][1]:
                    target_segment_idx = len(segments) - 1
                else:
                    continue
            
            # Переключить сегмент если нужно
            current_idx = self._current_segment_indices.get(camera, 0)
            if target_segment_idx != current_idx:
                new_segment = segments[target_segment_idx][2]
                # Преобразовать в абсолютный путь если нужно
                if not os.path.isabs(new_segment):
                    new_segment = os.path.abspath(new_segment)
                
                if os.path.exists(new_segment) and os.path.getsize(new_segment) > 1024:
                    player = self._video_players.get(camera)
                    if player:
                        player.stop()
                        if player.play_video(new_segment):
                            self._current_segments[camera] = new_segment
                            self._current_segment_indices[camera] = target_segment_idx
                        else:
                            self.logger.warning(f"Failed to switch to segment for camera {camera}: {new_segment}")
                else:
                    self.logger.debug(f"Segment file not found or invalid for camera {camera}: {new_segment}")
            
            # Установить позицию в сегменте
            segment_start = segments[target_segment_idx][0]
            segment_offset = (target_time - segment_start).total_seconds()
            segment_offset_ms = int(segment_offset * 1000)
            
            player = self._video_players.get(camera)
            if player:
                self._seek_player(player, segment_offset_ms)
    
    def _seek_player(self, player: VideoPlayerWidget, position_ms: int):
        """Перемотать конкретный плеер на позицию"""
        if hasattr(player, 'player') and player.player:
            # QMediaPlayer
            if pyqt_version == 6:
                player.player.setPosition(position_ms)
            else:
                player.player.setPosition(position_ms)
        elif hasattr(player, 'cap') and player.cap:
            # OpenCV
            import cv2
            fps = player.cap.get(cv2.CAP_PROP_FPS) or 30
            frame_number = int((position_ms / 1000.0) * fps)
            player.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    
    def set_playback_speed(self, speed: float):
        """Установить скорость воспроизведения"""
        self._playback_speed = speed
        
        for player in self._video_players.values():
            if hasattr(player, 'player') and player.player:
                # QMediaPlayer поддерживает setPlaybackRate
                try:
                    if pyqt_version == 6:
                        player.player.setPlaybackRate(speed)
                    else:
                        player.player.setPlaybackRate(speed)
                except Exception:
                    # Если не поддерживается, изменить интервал таймера
                    pass
            elif hasattr(player, 'timer') and player.timer:
                # OpenCV - изменить интервал таймера
                if hasattr(player, 'cap') and player.cap:
                    import cv2
                    fps = player.cap.get(cv2.CAP_PROP_FPS) or 30
                    base_interval = int(1000 / fps)
                    new_interval = int(base_interval / speed)
                    if new_interval > 0:
                        player.timer.setInterval(new_interval)


class TimelineWidget(QWidget):
    """Виджет временной шкалы с метками событий"""
    
    position_changed = pyqtSignal(int)  # position in milliseconds
    filters_changed = pyqtSignal(dict)  # event filters
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_module_logger("timeline")
        
        self._start_time = None
        self._end_time = None
        self._events = []
        self._event_filters = {}
        self._current_position_ms = 0
        
        self._init_ui()
        
    def _init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Фильтры событий
        filters_group = QGroupBox("Фильтры событий")
        filters_layout = QHBoxLayout()
        
        self.filter_checkboxes = {}
        event_types = {
            'camera_events': 'События камер',
            'system_events': 'Системные события',
            'zone_events_entered': 'Вход в зону',
            'zone_events_left': 'Выход из зоны'
        }
        
        for event_type, label in event_types.items():
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self._on_filter_changed)
            self.filter_checkboxes[event_type] = checkbox
            filters_layout.addWidget(checkbox)
        
        filters_layout.addStretch()
        filters_group.setLayout(filters_layout)
        layout.addWidget(filters_group)
        
        # Временная шкала
        timeline_group = QGroupBox("Временная шкала")
        timeline_layout = QVBoxLayout()
        
        # Отображение времени
        time_layout = QHBoxLayout()
        self.time_label = QLabel("00:00:00 / 00:00:00")
        time_layout.addWidget(self.time_label)
        time_layout.addStretch()
        timeline_layout.addLayout(time_layout)
        
        # Контейнер для слайдера и меток
        slider_container = QWidget()
        slider_layout = QVBoxLayout(slider_container)
        slider_layout.setContentsMargins(0, 0, 0, 0)
        slider_layout.setSpacing(0)
        
        # Метки событий (отображаются над слайдером)
        self.markers_widget = EventMarkersWidget()
        self.markers_widget.setFixedHeight(20)
        self.markers_widget.setStyleSheet("background-color: transparent;")
        slider_layout.addWidget(self.markers_widget)
        
        # Слайдер
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(1000)
        self.slider.valueChanged.connect(self._on_slider_changed)
        slider_layout.addWidget(self.slider)
        
        timeline_layout.addWidget(slider_container)
        
        timeline_group.setLayout(timeline_layout)
        layout.addWidget(timeline_group)
        
    def set_time_range(self, start_time: datetime.datetime, end_time: datetime.datetime):
        """Установить временной диапазон"""
        self._start_time = start_time
        self._end_time = end_time
        
        total_seconds = (end_time - start_time).total_seconds()
        self.slider.setMaximum(int(total_seconds * 1000))
        
        self._update_time_label()
        self._update_markers()
        
    def set_events(self, events: List[Dict], filters: Dict[str, bool]):
        """Установить события для отображения"""
        self._events = events
        self._event_filters = filters
        self._update_markers()
        
    def set_position(self, position_ms: int):
        """Установить позицию на временной шкале"""
        if position_ms != self._current_position_ms:
            self._current_position_ms = position_ms
            self.slider.blockSignals(True)
            self.slider.setValue(position_ms)
            self.slider.blockSignals(False)
            self._update_time_label()
    
    def _on_slider_changed(self, value: int):
        """Обработка изменения слайдера"""
        self._current_position_ms = value
        self._update_time_label()
        self.position_changed.emit(value)
    
    def _on_filter_changed(self):
        """Обработка изменения фильтров"""
        filters = {}
        for event_type, checkbox in self.filter_checkboxes.items():
            filters[event_type] = checkbox.isChecked()
        self.filters_changed.emit(filters)
        self._update_markers()
    
    def _update_time_label(self):
        """Обновить метку времени"""
        if self._start_time is None:
            return
        
        current_time = self._start_time + datetime.timedelta(milliseconds=self._current_position_ms)
        total_time = self._end_time - self._start_time if self._end_time else datetime.timedelta(0)
        
        current_str = current_time.strftime('%H:%M:%S')
        total_str = str(total_time).split('.')[0] if total_time.total_seconds() > 0 else "00:00:00"
        
        self.time_label.setText(f"{current_str} / {total_str}")
    
    def _update_markers(self):
        """Обновить отображение меток событий"""
        if not self._start_time or not self._end_time:
            return
        
        self.markers_widget.set_data(
            self._events,
            self._event_filters,
            self._start_time,
            self._end_time
        )
        self.markers_widget.update()


class EventMarkersWidget(QWidget):
    """Виджет для отображения меток событий на временной шкале"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._events = []
        self._event_filters = {}
        self._start_time = None
        self._end_time = None
        
    def set_data(self, events: List[Dict], filters: Dict[str, bool],
                 start_time: datetime.datetime, end_time: datetime.datetime):
        """Установить данные для отрисовки"""
        self._events = events
        self._event_filters = filters
        self._start_time = start_time
        self._end_time = end_time
        
    def paintEvent(self, event):
        """Отрисовать метки событий"""
        super().paintEvent(event)
        
        if not self._events or not self._start_time or not self._end_time:
            return
        
        try:
            from PyQt6.QtGui import QPainter, QColor, QPen
        except ImportError:
            from PyQt5.QtGui import QPainter, QColor, QPen
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        widget_width = self.width()
        widget_height = self.height()
        total_ms = (self._end_time - self._start_time).total_seconds() * 1000
        
        if total_ms <= 0:
            painter.end()
            return
        
        # Цвета для разных типов событий
        event_colors = {
            'camera_events': QColor(255, 100, 100),
            'system_events': QColor(100, 255, 100),
            'zone_events_entered': QColor(100, 100, 255),
            'zone_events_left': QColor(255, 255, 100)
        }
        
        # Отфильтровать события
        filtered_events = []
        for event in self._events:
            event_type = event.get('event_type', '')
            if self._event_filters.get(event_type, True):
                filtered_events.append(event)
        
        # Отрисовать метки
        for event in filtered_events:
            event_type = event.get('event_type', '')
            timestamp_str = event.get('ts') or event.get('timestamp')
            
            if not timestamp_str:
                continue
            
            try:
                if isinstance(timestamp_str, str):
                    # Парсинг ISO формата
                    if 'T' in timestamp_str:
                        event_time = datetime.datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    else:
                        continue
                else:
                    continue
                
                # Вычислить позицию метки
                time_diff = (event_time - self._start_time).total_seconds() * 1000
                if 0 <= time_diff <= total_ms:
                    x_pos = int((time_diff / total_ms) * widget_width)
                    
                    # Цвет метки
                    color = event_colors.get(event_type, QColor(200, 200, 200))
                    pen = QPen(color, 2)
                    painter.setPen(pen)
                    
                    # Отрисовать вертикальную линию
                    painter.drawLine(x_pos, 0, x_pos, widget_height)
                    
            except Exception as e:
                pass  # Игнорировать ошибки парсинга
        
        painter.end()


class PlaybackControlsWidget(QWidget):
    """Виджет контролов воспроизведения"""
    
    play_clicked = pyqtSignal()
    pause_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()
    speed_changed = pyqtSignal(float)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_module_logger("playback_controls")
        
        self._current_speed = 1.0
        
        self._init_ui()
        
    def _init_ui(self):
        """Инициализация интерфейса"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Кнопки управления
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.clicked.connect(self.play_clicked.emit)
        layout.addWidget(self.play_btn)
        
        self.pause_btn = QPushButton("⏸ Pause")
        self.pause_btn.clicked.connect(self.pause_clicked.emit)
        layout.addWidget(self.pause_btn)
        
        self.stop_btn = QPushButton("⏹ Stop")
        self.stop_btn.clicked.connect(self.stop_clicked.emit)
        layout.addWidget(self.stop_btn)
        
        layout.addStretch()
        
        # Выбор скорости
        layout.addWidget(QLabel("Скорость:"))
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["x0.5", "x1", "x2", "x4", "x8"])
        self.speed_combo.setCurrentIndex(1)  # x1 по умолчанию
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        layout.addWidget(self.speed_combo)
        
    def _on_speed_changed(self, index: int):
        """Обработка изменения скорости"""
        speeds = [0.5, 1.0, 2.0, 4.0, 8.0]
        if 0 <= index < len(speeds):
            self._current_speed = speeds[index]
            self.speed_changed.emit(self._current_speed)
