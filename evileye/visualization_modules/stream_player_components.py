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
        QGroupBox, QScrollArea, QButtonGroup, QDateEdit, QSizePolicy, QMenu
    )
    from PyQt6.QtCore import Qt, pyqtSignal, QDate, QPoint
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QPushButton, QSlider, QCheckBox, QComboBox, QSpinBox,
        QGroupBox, QScrollArea, QButtonGroup, QDateEdit, QSizePolicy, QMenu
    )
    from PyQt5.QtCore import Qt, pyqtSignal, QDate, QPoint
    pyqt_version = 5

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from ..core.logger import get_module_logger
from .video_player_window import VideoPlayerWidget
import logging

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None


class SourceSelectionMenu(QMenu):
    """Popup меню для выбора источника видео"""
    
    def __init__(self, available_sources: List[str], selected_sources: List[str], parent=None):
        super().__init__(parent)
        self._available_sources = available_sources
        self._selected_sources = selected_sources
        self._selected_action = None
        
        self._build_menu()
    
    def _build_menu(self):
        """Построить меню с доступными источниками"""
        if not self._available_sources:
            no_sources_action = self.addAction("No sources available")
            no_sources_action.setEnabled(False)
            return
        
        # Добавить действие "Очистить ячейку"
        clear_action = self.addAction("Clear cell")
        clear_action.setData(None)
        
        self.addSeparator()
        
        # Добавить все доступные источники
        for source in self._available_sources:
            action = self.addAction(source)
            action.setData(source)
            action.setCheckable(True)
            # Отметить выбранные источники
            if source in self._selected_sources:
                action.setChecked(True)


class CameraSelectorWidget(QWidget):
    """Виджет для выбора камер и даты"""
    
    cameras_selected = pyqtSignal(list)
    date_selected = pyqtSignal(str)
    
    def __init__(self, base_dir: str, parent=None, source_config: Dict = None):
        super().__init__(parent)
        self.logger = get_module_logger("camera_selector")
        self.base_dir = base_dir
        self.streams_dir = os.path.join(base_dir, 'Streams')
        self._source_config = source_config or {}
        
        self._available_dates = []
        self._available_cameras = {}
        self._available_sources = []  # Все доступные источники (включая разделенные)
        self._selected_cameras = []
        
        self._init_ui()
        self._load_available_dates()
        
    def _init_ui(self):
        """Инициализация интерфейса"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Группа выбора даты
        date_group = QGroupBox("Date")
        date_layout = QVBoxLayout()
        
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.dateChanged.connect(self._on_date_changed)
        date_layout.addWidget(self.date_edit)
        
        date_group.setLayout(date_layout)
        layout.addWidget(date_group)
        
        # Группа выбора камер (упрощенная - только кнопки, выбор через правый клик на ячейки)
        cameras_group = QGroupBox("Sources")
        cameras_layout = QVBoxLayout()
        
        # Информационная метка
        info_label = QLabel("Right-click on grid cells to select sources")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: gray; font-style: italic; padding: 5px;")
        cameras_layout.addWidget(info_label)
        
        # Кнопки управления
        buttons_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self._select_all)
        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        buttons_layout.addWidget(self.select_all_btn)
        buttons_layout.addWidget(self.deselect_all_btn)
        cameras_layout.addLayout(buttons_layout)
        
        cameras_group.setLayout(cameras_layout)
        layout.addWidget(cameras_group, stretch=1)
        
        # Группа настроек сетки
        grid_group = QGroupBox("Video Grid")
        grid_layout = QHBoxLayout()
        
        grid_layout.addWidget(QLabel("Rows:"))
        self.rows_spin = QSpinBox()
        self.rows_spin.setMinimum(1)
        self.rows_spin.setMaximum(4)
        self.rows_spin.setValue(2)
        grid_layout.addWidget(self.rows_spin)
        
        grid_layout.addWidget(QLabel("Columns:"))
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
        
        # Найти все папки камер
        camera_folders = []
        for item in os.listdir(date_dir):
            item_path = os.path.join(date_dir, item)
            if os.path.isdir(item_path):
                # Проверить наличие видео файлов
                video_files = glob.glob(os.path.join(item_path, '*.mp4'))
                if video_files:
                    camera_folders.append(item)
        
        self._available_cameras[date] = sorted(camera_folders)
        
        # Построить список всех доступных источников (включая разделенные)
        self._available_sources = []
        for camera_folder in self._available_cameras[date]:
            split_config = self._source_config.get(camera_folder)
            if split_config and split_config.get('split', False):
                # Разделенный поток - добавить отдельные источники
                source_names = split_config.get('source_names', [])
                num_split = split_config.get('num_split', 0)
                self._available_sources.extend(source_names[:num_split])
            else:
                # Обычный поток
                self._available_sources.append(camera_folder)
        
        self.logger.info(f"Loaded {len(camera_folders)} camera folders and {len(self._available_sources)} sources for date {date}")
        
    def _select_all(self):
        """Выбрать все источники (отправить сигнал)"""
        # Отправить сигнал со всеми доступными источниками
        if self._available_sources:
            self.cameras_selected.emit(self._available_sources.copy())
        
    def _deselect_all(self):
        """Снять выбор со всех источников"""
        self.cameras_selected.emit([])
    
    def get_selected_date(self) -> str:
        """Получить выбранную дату"""
        date = self.date_edit.date()
        return date.toString('yyyy-MM-dd')
    
    def get_grid_size(self) -> Tuple[int, int]:
        """Получить размер сетки"""
        return (self.rows_spin.value(), self.cols_spin.value())
    
    def set_grid_size(self, rows: int, cols: int):
        """Установить размер сетки (синхронизация с реальным размером)"""
        # Обновить значения спинбоксов без отправки сигнала
        self.rows_spin.blockSignals(True)
        self.cols_spin.blockSignals(True)
        self.rows_spin.setValue(rows)
        self.cols_spin.setValue(cols)
        self.rows_spin.blockSignals(False)
        self.cols_spin.blockSignals(False)
        self.logger.debug(f"Grid size UI updated to {rows}x{cols}")


class VideoGridWidget(QWidget):
    """Виджет сетки видео NxM"""
    
    position_changed = pyqtSignal(int)  # position in milliseconds
    source_selected = pyqtSignal(int, str)  # (grid_index, source_name) - сигнал выбора источника для ячейки
    grid_size_changed = pyqtSignal(int, int)  # (rows, cols) - сигнал изменения размера сетки
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_module_logger("video_grid")
        
        self._cameras = []
        self._camera_segments = {}  # {camera: [(start_time, end_time, path)]}
        self._video_players = {}  # {camera_name: VideoPlayerWidget or SplitVideoPlayerWidget}
        self._current_segments = {}  # {camera_name: current_segment_path}
        self._current_segment_indices = {}  # {camera_name: index in segments list}
        self._playback_speed = 1.0
        self._start_time = None  # datetime начала общего временного диапазона
        self._source_config = {}  # Конфигурация источников для разделения
        self._available_sources = []  # Список всех доступных источников
        self._grid_cell_sources = {}  # {grid_index: source_name} - маппинг ячеек к источникам
        self._grid_cell_widgets = {}  # {grid_index: widget} - виджеты в ячейках
        self._last_widget_sizes = {}  # {widget_id: (width, height)} - для отслеживания изменений размеров
        
        # Состояние полноэкранного режима
        self._fullscreen_cell_index = None  # Индекс ячейки в полноэкранном режиме
        self._saved_grid_state = {}  # Сохраненное состояние сетки: {grid_idx: {'widget': widget, 'row': row, 'col': col, 'rowspan': rowspan, 'colspan': colspan, 'visible': visible}}
        
        # Таймер для периодической проверки размеров виджетов
        try:
            from PyQt6.QtCore import QTimer
        except ImportError:
            from PyQt5.QtCore import QTimer
        self._size_check_timer = QTimer()
        self._size_check_timer.timeout.connect(self._check_widget_sizes)
        self._size_check_timer.setInterval(1000)  # Проверять каждую секунду
        
        self._init_ui()
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # Для получения событий клавиатуры
        
    def _init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(4)
        # Установить размеры сетки по умолчанию для предотвращения проблем с растяжением
        self.grid_layout.setRowStretch(0, 0)
        self.grid_layout.setColumnStretch(0, 0)
        
        container = QWidget()
        container.setLayout(self.grid_layout)
        layout.addWidget(container)
        
        # Инициализировать stretch factors (будут обновлены в set_cameras)
        self._rows = 2
        self._cols = 2
        
    def set_cameras(self, cameras: List[str], camera_segment_times: Dict[str, List[Tuple]], source_config: Dict = None, base_dir: str = None, date_folder: str = None):
        """Установить камеры и их сегменты с поддержкой разделенных потоков"""
        self._cameras = cameras
        self._camera_segments = camera_segment_times  # Используем camera_segment_times как camera_segments
        self._source_config = source_config or {}
        self._base_dir = base_dir
        self._date_folder = date_folder
        
        # Построить список всех доступных источников (включая разделенные)
        self._available_sources = []
        for camera in cameras:
            split_config = self._source_config.get(camera)
            if split_config and split_config.get('split', False):
                source_names = split_config.get('source_names', [])
                self._available_sources.extend(source_names[:split_config.get('num_split', 0)])
            else:
                self._available_sources.append(camera)
        
        # Очистить существующие виджеты
        self._clear_grid()
        
        if not cameras:
            return
        
        # Определить все источники (включая разделенные)
        all_sources = []  # [(camera_folder, source_name, is_split, split_index)]
        
        for camera in cameras:
            split_config = self._source_config.get(camera)
            if split_config and split_config.get('split', False):
                # Разделенный поток - добавить все источники
                source_names = split_config.get('source_names', [])
                num_split = split_config.get('num_split', 0)
                for i in range(num_split):
                    source_name = source_names[i] if i < len(source_names) else f"{camera}_src{i}"
                    all_sources.append((camera, source_name, True, i))
            else:
                # Обычный поток
                all_sources.append((camera, camera, False, None))
        
        # Определить размер сетки на основе уникальных папок камер (не всех источников)
        # Сначала нужно определить уникальные папки, чтобы правильно рассчитать размер сетки
        # Временная группировка для расчета размера сетки
        temp_folder_to_sources = {}
        for camera in cameras:
            if camera not in camera_segment_times:
                continue
            split_config = self._source_config.get(camera)
            if split_config and split_config.get('split', False):
                parent_folder = split_config.get('parent_folder')
                if parent_folder:
                    if parent_folder not in temp_folder_to_sources:
                        temp_folder_to_sources[parent_folder] = []
                    temp_folder_to_sources[parent_folder].append(camera)
                else:
                    source_names = split_config.get('source_names', [])
                    if source_names:
                        composite_name = '-'.join(source_names[:split_config.get('num_split', len(source_names))])
                        if composite_name not in temp_folder_to_sources:
                            temp_folder_to_sources[composite_name] = []
                        temp_folder_to_sources[composite_name].append(camera)
                    else:
                        if camera not in temp_folder_to_sources:
                            temp_folder_to_sources[camera] = []
                        temp_folder_to_sources[camera].append(camera)
            else:
                if camera not in temp_folder_to_sources:
                    temp_folder_to_sources[camera] = []
                temp_folder_to_sources[camera].append(camera)
        
        # Рассчитать размер сетки с учетом rowspan для split players
        total_folders = len(temp_folder_to_sources)
        
        # Сначала определить max_rowspan для split players
        max_rowspan = 1
        num_split_players = 0
        num_regular_players = 0
        
        for folder, sources in temp_folder_to_sources.items():
            split_config = self._source_config.get(folder)
            if not split_config:
                # Попробовать найти по первому источнику
                if sources:
                    split_config = self._source_config.get(sources[0])
            
            if split_config and split_config.get('split', False):
                num_split = split_config.get('num_split', 1)
                max_rowspan = max(max_rowspan, num_split)
                num_split_players += 1
            else:
                num_regular_players += 1
        
        # Рассчитать базовый размер сетки на основе общего количества виджетов
        # Но учитывать, что split players занимают больше места
        # Эффективное количество "ячеек" = обычные виджеты + split players * max_rowspan
        effective_cells = num_regular_players + num_split_players * max_rowspan
        
        # Рассчитать размер сетки на основе эффективного количества ячеек
        rows = 2
        cols = 2
        if effective_cells == 1:
            rows, cols = 1, 1
        elif effective_cells <= 2:
            rows, cols = 1, 2
        elif effective_cells <= 4:
            rows, cols = 2, 2
        elif effective_cells <= 6:
            rows, cols = 2, 3
        elif effective_cells <= 9:
            rows, cols = 3, 3
        elif effective_cells <= 12:
            rows, cols = 3, 4
        elif effective_cells <= 16:
            rows, cols = 4, 4
        else:
            # Для большего количества - использовать квадратную сетку
            import math
            grid_size = int(math.ceil(math.sqrt(effective_cells)))
            rows, cols = grid_size, grid_size
        
        # Убедиться, что строк достаточно для размещения split players
        # Каждый split player занимает max_rowspan строк
        if max_rowspan > 1:
            # Минимальное количество строк = max_rowspan
            # Но нужно учесть, что split players могут размещаться в несколько рядов
            if num_split_players > 0:
                # Если split players размещаются в несколько колонок, нужно больше строк
                if num_split_players > cols:
                    # Split players размещаются в несколько рядов
                    num_rows_of_split_players = ((num_split_players + cols - 1) // cols)
                    rows_needed = max_rowspan * num_rows_of_split_players
                else:
                    # Все split players помещаются в один ряд, но каждый занимает max_rowspan строк
                    rows_needed = max_rowspan
                
                rows = max(rows, rows_needed)
        
        self.logger.info(
            f"Calculated grid size: {rows}x{cols} "
            f"(total_folders={total_folders}, num_split_players={num_split_players}, "
            f"num_regular_players={num_regular_players}, max_rowspan={max_rowspan}, "
            f"effective_cells={effective_cells})"
        )
        
        # Сохранить размеры сетки
        self._rows = rows
        self._cols = cols
        
        # Отправить сигнал об изменении размера сетки
        self.grid_size_changed.emit(rows, cols)
        
        # Сначала сбросить все stretch factors
        for col in range(cols):
            self.grid_layout.setColumnStretch(col, 0)
        for row in range(rows):
            self.grid_layout.setRowStretch(row, 0)
        
        # Определить общее время начала
        if camera_segment_times:
            all_starts = []
            for segments in camera_segment_times.values():
                if segments:
                    all_starts.append(segments[0][0])
            if all_starts:
                self._start_time = min(all_starts)
        
        # Группировать источники по папкам камер для разделенных потоков
        camera_groups = {}  # {camera_folder: [source_indices]}
        for idx, (camera_folder, source_name, is_split, split_index) in enumerate(all_sources):
            if camera_folder not in camera_groups:
                camera_groups[camera_folder] = []
            camera_groups[camera_folder].append(idx)
        
        # Определить уникальные папки камер (для split streams - использовать parent_folder)
        # Группировать источники по папкам
        folder_to_sources = {}  # {folder_name: [source_names]}
        
        for camera in cameras:
            if camera not in camera_segment_times:
                continue
            
            split_config = self._source_config.get(camera)
            if split_config and split_config.get('split', False):
                # Для разделенных потоков использовать parent_folder или составное имя
                parent_folder = split_config.get('parent_folder')
                if parent_folder:
                    if parent_folder not in folder_to_sources:
                        folder_to_sources[parent_folder] = []
                    if camera not in folder_to_sources[parent_folder]:
                        folder_to_sources[parent_folder].append(camera)
                else:
                    # Если parent_folder нет, попробовать составить имя из source_names
                    source_names = split_config.get('source_names', [])
                    if source_names:
                        composite_name = '-'.join(source_names[:split_config.get('num_split', len(source_names))])
                        if composite_name not in folder_to_sources:
                            folder_to_sources[composite_name] = []
                        if camera not in folder_to_sources[composite_name]:
                            folder_to_sources[composite_name].append(camera)
                    else:
                        # Fallback: использовать имя камеры
                        if camera not in folder_to_sources:
                            folder_to_sources[camera] = []
                        folder_to_sources[camera].append(camera)
            else:
                # Обычный поток
                if camera not in folder_to_sources:
                    folder_to_sources[camera] = []
                folder_to_sources[camera].append(camera)
        
        unique_camera_folders = list(folder_to_sources.keys())
        self.logger.info(f"Grouped cameras into folders: {folder_to_sources}")
        
        # Создать виджеты видео для каждой уникальной папки камеры
        # Использовать матрицу занятости для правильного размещения split players
        occupied = [[False for _ in range(cols)] for _ in range(rows)]
        
        for camera_folder in unique_camera_folders:
            # Найти конфигурацию и сегменты для этой папки
            split_config = None
            actual_camera_name = None
            segments_to_use = None
            
            # Найти источники для этой папки
            sources_for_folder = folder_to_sources.get(camera_folder, [])
            if not sources_for_folder:
                self.logger.warning(f"No sources found for folder: {camera_folder}")
                continue
            
            # Использовать первый источник для получения сегментов и конфигурации
            first_source = sources_for_folder[0]
            actual_camera_name = first_source
            segments_to_use = camera_segment_times.get(first_source)
            
            # Найти конфигурацию для этой папки
            split_config = None
            if camera_folder in self._source_config:
                split_config = self._source_config[camera_folder]
            else:
                # Попробовать найти конфигурацию по первому источнику
                split_config = self._source_config.get(first_source)
                if split_config and split_config.get('split', False):
                    # Проверить, что parent_folder совпадает
                    parent = split_config.get('parent_folder')
                    if parent != camera_folder:
                        # Попробовать найти конфигурацию по составному имени
                        source_names = split_config.get('source_names', [])
                        if source_names:
                            composite_name = '-'.join(source_names[:split_config.get('num_split', len(source_names))])
                            if composite_name == camera_folder:
                                # Использовать эту конфигурацию
                                pass
                            else:
                                # Поиск по другим источникам
                                for src in sources_for_folder:
                                    config = self._source_config.get(src)
                                    if config and config.get('split', False):
                                        parent = config.get('parent_folder')
                                        if parent == camera_folder:
                                            split_config = config
                                            break
            
            if not actual_camera_name or not segments_to_use:
                self.logger.warning(
                    f"Could not find camera segments for folder: {camera_folder}, "
                    f"actual_camera_name={actual_camera_name}, segments_to_use={segments_to_use is not None}"
                )
                continue
            
            is_split = split_config and split_config.get('split', False)
            
            # Найти первую свободную позицию в сетке
            row, col = -1, -1
            for r in range(rows):
                for c in range(cols):
                    if not occupied[r][c]:
                        row, col = r, c
                        break
                if row >= 0:
                    break
            
            if row < 0 or col < 0:
                self.logger.warning(f"No free position in grid for {camera_folder}")
                continue
            
            if is_split:
                # Разделенный поток - создать отдельные ячейки для каждой области
                num_split = split_config.get('num_split', 1)
                source_names = split_config.get('source_names', [])
                
                # Создать один SplitVideoPlayerWidget для декодирования (скрытый)
                split_player = SplitVideoPlayerWidget(parent=self)
                split_player.hide()  # Скрыть основной виджет
                split_player._external_mode = True  # Режим внешнего использования виджетов
                
                # Загрузить первый сегмент
                if segments_to_use:
                    first_segment = segments_to_use[0][2] if isinstance(segments_to_use[0], tuple) else segments_to_use[0]
                    if not os.path.isabs(first_segment):
                        first_segment = os.path.abspath(first_segment)
                    
                    if os.path.exists(first_segment) and os.path.getsize(first_segment) > 1024:
                        self.logger.info(f"Calling set_split_config for {camera_folder} with video: {first_segment}")
                        config_result = split_player.set_split_config(split_config, first_segment)
                        self.logger.info(f"set_split_config returned: {config_result} for {camera_folder}")
                        
                        if config_result:
                            # Сохранить информацию о плеере (использовать имя папки как ключ)
                            self._video_players[camera_folder] = split_player
                            self._current_segments[camera_folder] = first_segment
                            self._current_segment_indices[camera_folder] = 0
                            self.logger.info(f"Split player {camera_folder} configured successfully")
                            
                            # Создать отдельные контейнеры для каждой области
                            for i in range(num_split):
                                # Найти свободную позицию для этой области
                                region_row, region_col = -1, -1
                                for r in range(rows):
                                    for c in range(cols):
                                        if not occupied[r][c]:
                                            region_row, region_col = r, c
                                            break
                                    if region_row >= 0:
                                        break
                                
                                if region_row < 0 or region_col < 0:
                                    self.logger.warning(f"No free position in grid for split region {i} of {camera_folder}")
                                    continue
                                
                                # Получить виджет области из split_player
                                if i < len(split_player._region_widgets):
                                    region_info = split_player._region_widgets[i]
                                    region_widget = region_info['widget']
                                    source_name = region_info.get('source_name', source_names[i] if i < len(source_names) else f"Source{i}")
                                    
                                    # Удалить виджет из его текущего контейнера (если он там есть)
                                    if region_info['container'].layout():
                                        region_info['container'].layout().removeWidget(region_widget)
                                    
                                    # Создать новый контейнер для этой области
                                    region_container = QWidget()
                                    region_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
                                    region_container.setStyleSheet("border: 2px solid #888888;")
                                    region_container.setMinimumSize(100, 100)
                                    region_layout = QVBoxLayout(region_container)
                                    region_layout.setContentsMargins(0, 0, 0, 0)
                                    region_layout.setSpacing(0)
                                    
                                    # Метка с именем источника
                                    label = QLabel(source_name)
                                    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                                    label.setStyleSheet("background-color: rgba(0, 0, 0, 200); color: white; padding: 3px; font-weight: bold;")
                                    region_layout.addWidget(label)
                                    
                                    # Добавить виджет области в новый контейнер
                                    region_layout.addWidget(region_widget, stretch=1)
                                    
                                    # Обновить ссылку на контейнер в region_info
                                    region_info['container'] = region_container
                                    
                                    # Добавить контейнер в сетку как отдельную ячейку
                                    grid_idx = region_row * cols + region_col
                                    self.grid_layout.addWidget(region_container, region_row, region_col)
                                    occupied[region_row][region_col] = True
                                    
                                    # Сохранить в маппинге
                                    self._grid_cell_sources[grid_idx] = source_name
                                    self._grid_cell_widgets[grid_idx] = region_container
                                    
                                    # Добавить обработчик двойного клика для полноэкранного режима
                                    def on_region_double_click(event, grid_idx=grid_idx):
                                        if self._fullscreen_cell_index is None:
                                            # Войти в полноэкранный режим
                                            self._enter_fullscreen_mode(grid_idx)
                                        elif self._fullscreen_cell_index == grid_idx:
                                            # Выйти из полноэкранного режима
                                            self._exit_fullscreen_mode()
                                        event.accept()
                                    
                                    region_container.mouseDoubleClickEvent = on_region_double_click
                                    
                                    self.logger.info(
                                        f"Added split region {i} ({source_name}) for {camera_folder} "
                                        f"at row={region_row}, col={region_col}, grid_idx={grid_idx}"
                                    )
                        else:
                            self.logger.error(f"Failed to configure split player for {camera_folder}")
                    else:
                        self.logger.warning(f"Video file not found for split camera {camera_folder}")
            else:
                # Обычный поток - создать обычный VideoPlayerWidget
                # Найти первую свободную позицию (уже найдена выше)
                if row < 0 or col < 0:
                    continue
                
                # Использовать actual_camera_name если есть, иначе camera_folder
                camera_name = actual_camera_name if actual_camera_name else camera_folder
                
                # Вычислить grid_idx до создания замыкания
                grid_idx = row * cols + col
                
                # Создать контейнер для видео и метки
                container_widget = QWidget()
                container_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
                container_widget.setStyleSheet("border: 2px solid #888888;")
                container_widget.setMinimumSize(100, 100)  # Минимальный размер для предотвращения слишком маленьких виджетов
                container_widget.setMaximumSize(16777215, 16777215)  # Установить максимальный размер (Qt default)
                
                # Добавить обработчик изменения размера для диагностики
                original_resize = container_widget.resizeEvent
                def on_container_resize(event, cam=camera_name, idx=grid_idx):
                    size = container_widget.size()
                    geometry = container_widget.geometry()
                    self.logger.warning(
                        f"Container widget resize: camera={cam}, grid_idx={idx}, "
                        f"size={size.width()}x{size.height()}, "
                        f"geometry={geometry.x()},{geometry.y()} {geometry.width()}x{geometry.height()}"
                    )
                    original_resize(event)
                
                container_widget.resizeEvent = on_container_resize
                
                # Добавить обработчик двойного клика для полноэкранного режима
                def on_container_double_click(event, grid_idx=grid_idx):
                    if self._fullscreen_cell_index is None:
                        # Войти в полноэкранный режим
                        self._enter_fullscreen_mode(grid_idx)
                    elif self._fullscreen_cell_index == grid_idx:
                        # Выйти из полноэкранного режима
                        self._exit_fullscreen_mode()
                    event.accept()
                
                container_widget.mouseDoubleClickEvent = on_container_double_click
                
                container_layout = QVBoxLayout(container_widget)
                container_layout.setContentsMargins(0, 0, 0, 0)
                container_layout.setSpacing(0)
                
                # Метка с именем камеры
                label = QLabel(camera_name)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setStyleSheet("background-color: rgba(0, 0, 0, 200); color: white; padding: 3px; font-weight: bold;")
                container_layout.addWidget(label)
                
                # Создать виджет видео
                video_widget = VideoPlayerWidget(parent=container_widget, logger_name=f"camera_{camera_name}")
                video_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
                self._video_players[camera_name] = video_widget
                container_layout.addWidget(video_widget, stretch=1)
                
                # Настроить метаданные для плеера
                if self._base_dir and self._date_folder:
                    video_widget.set_metadata_config(self._base_dir, self._date_folder, camera_name)
                
                # Загрузить первый сегмент
                if camera_segment_times.get(camera_name):
                    first_segment = camera_segment_times[camera_name][0][2]
                    if not os.path.isabs(first_segment):
                        first_segment = os.path.abspath(first_segment)
                    
                    if os.path.exists(first_segment) and os.path.getsize(first_segment) > 1024:
                        if video_widget.play_video(first_segment):
                            self._current_segments[camera_name] = first_segment
                            self._current_segment_indices[camera_name] = 0
                        else:
                            self.logger.warning(f"Failed to play video for camera {camera_name}: {first_segment}")
                    else:
                        self.logger.warning(f"Video file not found or too small for camera {camera_name}: {first_segment}")
                
                # Добавить контейнер в сетку
                self.logger.info(
                    f"Adding container widget for {camera_name} at row={row}, col={col}, grid_idx={grid_idx}"
                )
                self.grid_layout.addWidget(container_widget, row, col)
                
                # Отметить занятую ячейку
                occupied[row][col] = True
                
                # Сохранить виджет в маппинге (grid_idx уже вычислен выше)
                self._grid_cell_sources[grid_idx] = camera_name
                self._grid_cell_widgets[grid_idx] = container_widget
        
        # Вычислить максимальный размер виджетов на основе размера сетки и доступного пространства
        # Это предотвращает бесконечный рост виджетов
        if self.width() > 0 and self.height() > 0:
            # Использовать текущий размер виджета сетки
            available_width = self.width()
            available_height = self.height()
        else:
            # Если размер еще не установлен, использовать размер по умолчанию
            available_width = 1400
            available_height = 600
        
        # Учесть spacing и margins
        spacing = self.grid_layout.spacing()
        margins = self.grid_layout.contentsMargins()
        usable_width = available_width - margins.left() - margins.right() - spacing * (cols - 1)
        usable_height = available_height - margins.top() - margins.bottom() - spacing * (rows - 1)
        
        # Максимальный размер виджета = размер ячейки сетки
        max_widget_width = usable_width // cols if cols > 0 else usable_width
        max_widget_height = usable_height // rows if rows > 0 else usable_height
        
        # Установить максимальный размер для всех виджетов
        for grid_idx, widget in self._grid_cell_widgets.items():
            if widget:
                widget.setMaximumSize(max_widget_width, max_widget_height)
                self.logger.debug(
                    f"Set maximum size for widget {grid_idx}: {max_widget_width}x{max_widget_height}"
                )
        
        # Установить stretch factors ПОСЛЕ добавления всех виджетов для равномерного распределения
        # Использовать более умное распределение на основе типов виджетов
        self.logger.info(f"Setting stretch factors: rows={rows}, cols={cols}")
        
        # Определить, какие строки содержат split players (rowspan > 1)
        rows_with_split_players = set()
        for i in range(self.grid_layout.count()):
            item = self.grid_layout.itemAt(i)
            if item and item.widget():
                try:
                    position = self.grid_layout.getItemPosition(i)
                    row, col, rowspan, colspan = position
                    if rowspan > 1:
                        # Отметить все строки, занятые этим split player
                        for r in range(row, min(row + rowspan, rows)):
                            rows_with_split_players.add(r)
                except (AttributeError, TypeError):
                    pass
        
        # Установить stretch factors для колонок - равномерно
        for col in range(cols):
            self.grid_layout.setColumnStretch(col, 1)
            self.logger.debug(f"  Column {col} stretch = 1")
        
        # Установить stretch factors для строк - учитывая split players
        for row in range(rows):
            if row in rows_with_split_players:
                # Строки с split players получают больший stretch для правильного распределения
                self.grid_layout.setRowStretch(row, 2)
                self.logger.debug(f"  Row {row} stretch = 2 (contains split player)")
            else:
                # Обычные строки получают стандартный stretch
                self.grid_layout.setRowStretch(row, 1)
                self.logger.debug(f"  Row {row} stretch = 1")
        
        # Логировать размеры всех виджетов после добавления
        self._log_widget_sizes("after set_cameras")
        
        # Запустить таймер для периодической проверки размеров
        self._size_check_timer.start()
        
    def _check_widget_sizes(self):
        """Периодическая проверка размеров виджетов для обнаружения бесконечного роста"""
        if not self._grid_cell_widgets:
            return
        
        # Проверять виджеты напрямую из layout, а не из маппинга
        # Это более надежно, так как layout знает реальную структуру
        processed_widgets = set()
        for i in range(self.grid_layout.count()):
            item = self.grid_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                widget_id = id(widget)
                
                # Пропустить если уже обработали
                if widget_id in processed_widgets:
                    continue
                processed_widgets.add(widget_id)
                
                # Получить позицию из layout правильно
                try:
                    # QGridLayout.getItemPosition() возвращает (row, col, rowspan, colspan)
                    position = self.grid_layout.getItemPosition(i)
                    row, col, rowspan, colspan = position
                except (AttributeError, TypeError):
                    # Fallback: попробовать получить через itemAtPosition
                    row, col, rowspan, colspan = -1, -1, 1, 1
                    # Перебрать все позиции для поиска
                    for r in range(self._rows):
                        for c in range(self._cols):
                            layout_item = self.grid_layout.itemAtPosition(r, c)
                            if layout_item == item:
                                row, col = r, c
                                # Попробовать получить rowspan и colspan
                                try:
                                    if hasattr(layout_item, 'rowSpan'):
                                        rowspan = layout_item.rowSpan()
                                    if hasattr(layout_item, 'columnSpan'):
                                        colspan = layout_item.columnSpan()
                                except:
                                    pass
                                break
                        if row >= 0:
                            break
                
                size = widget.size()
                geometry = widget.geometry()
                
                # Найти имя камеры для этого виджета
                camera = "unknown"
                for grid_idx, w in self._grid_cell_widgets.items():
                    if w == widget:
                        camera = self._grid_cell_sources.get(grid_idx, "unknown")
                        break
                
                last_size = self._last_widget_sizes.get(widget_id)
                if last_size:
                    if size.width() > last_size[0] * 1.1 or size.height() > last_size[1] * 1.1:
                        # Размер увеличился более чем на 10%
                        self.logger.error(
                            f"WIDGET SIZE INCREASING: row={row}, col={col}, rowspan={rowspan}, colspan={colspan}, camera={camera}, "
                            f"size changed from {last_size[0]}x{last_size[1]} to {size.width()}x{size.height()}, "
                            f"geometry={geometry.x()},{geometry.y()} {geometry.width()}x{geometry.height()}"
                        )
                    elif size.width() != last_size[0] or size.height() != last_size[1]:
                        self.logger.debug(
                            f"Widget size changed: row={row}, col={col}, camera={camera}, "
                            f"{last_size[0]}x{last_size[1]} -> {size.width()}x{size.height()}"
                        )
                
                self._last_widget_sizes[widget_id] = (size.width(), size.height())
        
    def resizeEvent(self, event):
        """Обработка изменения размера виджета сетки"""
        super().resizeEvent(event)
        self.logger.debug(f"VideoGridWidget resizeEvent: new size = {event.size().width()}x{event.size().height()}")
        self._log_widget_sizes("on resizeEvent")
    
    def _log_widget_sizes(self, context: str):
        """Логировать размеры всех виджетов в сетке"""
        self.logger.info(f"=== Widget sizes {context} ===")
        self.logger.info(f"Grid size: {self._rows}x{self._cols}")
        self.logger.info(f"VideoGridWidget size: {self.width()}x{self.height()}")
        
        for grid_idx, widget in self._grid_cell_widgets.items():
            if widget:
                widget_id = id(widget)
                size = widget.size()
                geometry = widget.geometry()
                camera = self._grid_cell_sources.get(grid_idx, "unknown")
                
                # Проверить изменение размера
                last_size = self._last_widget_sizes.get(widget_id)
                if last_size and (last_size[0] != size.width() or last_size[1] != size.height()):
                    self.logger.warning(
                        f"  Widget {grid_idx} ({camera}) SIZE CHANGED: "
                        f"{last_size[0]}x{last_size[1]} -> {size.width()}x{size.height()}, "
                        f"geometry: {geometry.x()},{geometry.y()} {geometry.width()}x{geometry.height()}"
                    )
                else:
                    self.logger.info(
                        f"  Widget {grid_idx} ({camera}): "
                        f"size={size.width()}x{size.height()}, "
                        f"geometry={geometry.x()},{geometry.y()} {geometry.width()}x{geometry.height()}"
                    )
                
                self._last_widget_sizes[widget_id] = (size.width(), size.height())
        
        # Логировать размеры split players
        for camera, player in self._video_players.items():
            if isinstance(player, SplitVideoPlayerWidget):
                size = player.size()
                geometry = player.geometry()
                self.logger.info(
                    f"  SplitPlayer {camera}: "
                    f"size={size.width()}x{size.height()}, "
                    f"geometry={geometry.x()},{geometry.y()} {geometry.width()}x{geometry.height()}"
                )
        
    def _clear_grid(self):
        """Очистить сетку"""
        for camera, player in self._video_players.items():
            try:
                # Правильная последовательность очистки: stop() → освобождение ресурсов → deleteLater()
                if hasattr(player, 'stop'):
                    player.stop()
                
                # Для QMediaPlayer освободить ресурсы
                if hasattr(player, 'player') and player.player:
                    try:
                        if pyqt_version == 6:
                            from PyQt6.QtCore import QUrl
                            player.player.setSource(QUrl())
                        else:
                            from PyQt5.QtMultimedia import QMediaContent
                            player.player.setMedia(QMediaContent())
                    except Exception as e:
                        self.logger.debug(f"Error clearing player resources for {camera}: {e}")
                
                player.deleteLater()
            except Exception as e:
                self.logger.warning(f"Error clearing player for {camera}: {e}")
        
        self._video_players.clear()
        self._current_segments.clear()
        self._current_segment_indices.clear()
        self._grid_cell_sources.clear()
        self._grid_cell_widgets.clear()
        
        # Остановить таймер проверки размеров
        if hasattr(self, '_size_check_timer'):
            self._size_check_timer.stop()
        
        # Удалить все виджеты из layout
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Сбросить stretch factors для предотвращения накопления
        self.logger.debug(f"Clearing stretch factors: rows={self._rows}, cols={self._cols}")
        for col in range(self._cols):
            self.grid_layout.setColumnStretch(col, 0)
        for row in range(self._rows):
            self.grid_layout.setRowStretch(row, 0)
        
        self._last_widget_sizes.clear()
    
    def _on_context_menu(self, position: QPoint):
        """Обработка правого клика для выбора источника"""
        # Определить, в какой ячейке был клик
        grid_index = self._get_grid_index_at_position(position)
        if grid_index is None:
            return
        
        # Получить текущий источник в ячейке
        current_source = self._grid_cell_sources.get(grid_index)
        selected_sources = list(self._grid_cell_sources.values())
        
        # Создать и показать меню
        menu = SourceSelectionMenu(self._available_sources, selected_sources, self)
        action = menu.exec(self.mapToGlobal(position))
        
        if action and action.data() is not None:
            selected_source = action.data()
            # Отправить сигнал о выборе источника
            self.source_selected.emit(grid_index, selected_source)
        elif action and action.data() is None:
            # Очистить ячейку
            self.source_selected.emit(grid_index, None)
    
    def _get_grid_index_at_position(self, position: QPoint) -> Optional[int]:
        """Определить индекс ячейки сетки по позиции клика"""
        # Простой подход: перебрать все ячейки и проверить, попадает ли позиция в их границы
        for grid_idx, widget in self._grid_cell_widgets.items():
            widget_pos = widget.mapFromGlobal(self.mapToGlobal(position))
            if widget.rect().contains(widget_pos):
                return grid_idx
        return None
    
    def set_source_for_cell(self, grid_index: int, source_name: Optional[str]):
        """Установить источник для ячейки сетки (вызывается извне)"""
        # Это будет вызываться из StreamPlayerWindow при получении сигнала source_selected
        # Пока оставляем заглушку - полная реализация требует пересоздания виджетов
        self._grid_cell_sources[grid_index] = source_name
    
    def play_all(self):
        """Запустить воспроизведение всех видео"""
        self.logger.info(f"play_all() called with {len(self._video_players)} players")
        
        for camera, player in self._video_players.items():
            player_type = "SplitVideoPlayerWidget" if isinstance(player, SplitVideoPlayerWidget) else "VideoPlayerWidget"
            self.logger.info(f"play_all(): Processing camera={camera}, type={player_type}")
            
            # Проверить тип плеера
            if isinstance(player, SplitVideoPlayerWidget):
                self.logger.info(f"play_all(): Calling play() for split player {camera}")
                player.play()
            else:
                # Обычный VideoPlayerWidget
                # Проверить, загружено ли видео
                if not hasattr(player, 'video_path') or not player.video_path:
                    # Видео не загружено - попытаться загрузить первый сегмент
                    if camera in self._camera_segments and self._camera_segments[camera]:
                        first_segment = self._camera_segments[camera][0][2] if isinstance(self._camera_segments[camera][0], tuple) else self._camera_segments[camera][0]
                        if not os.path.isabs(first_segment):
                            first_segment = os.path.abspath(first_segment)
                        if os.path.exists(first_segment) and os.path.getsize(first_segment) > 1024:
                            if player.play_video(first_segment):
                                self._current_segments[camera] = first_segment
                                self._current_segment_indices[camera] = 0
                            else:
                                self.logger.warning(f"Failed to play video for camera {camera}: {first_segment}")
                                continue
                    else:
                        self.logger.warning(f"No segments available for camera {camera}")
                        continue
                
                # Запустить воспроизведение
                if hasattr(player, 'player') and player.player:
                    if pyqt_version == 6:
                        player.player.play()
                    else:
                        player.player.play()
                elif hasattr(player, 'timer') and player.timer:
                    if not player.timer.isActive():
                        player.timer.start()
                elif hasattr(player, '_use_opencv') and player._use_opencv:
                    # OpenCV режим - запустить таймер если он есть
                    if hasattr(player, 'timer') and player.timer:
                        if not player.timer.isActive():
                            player.timer.start()
                    elif hasattr(player, 'cap') and player.cap and player.cap.isOpened():
                        # Таймер не создан - создать и запустить
                        try:
                            from PyQt6.QtCore import QTimer
                        except ImportError:
                            from PyQt5.QtCore import QTimer
                        player.timer = QTimer()
                        player.timer.timeout.connect(player._update_frame_opencv)
                        if cv2:
                            fps = player.cap.get(cv2.CAP_PROP_FPS) or 30
                            interval = int(1000 / fps)
                            player.timer.start(interval)
    
    def pause_all(self):
        """Приостановить воспроизведение всех видео"""
        for player in self._video_players.values():
            if isinstance(player, SplitVideoPlayerWidget):
                player.pause()
            else:
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
            if isinstance(player, SplitVideoPlayerWidget):
                player.stop()
            else:
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
            
            # segments может быть списком кортежей (start_time, end_time, path) или списком путей
            # Проверить формат
            if isinstance(segments[0], tuple):
                # Формат кортежей
                pass
            else:
                # Формат путей - преобразовать в кортежи для совместимости
                segments = [(None, None, seg) for seg in segments]
            
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
                        if isinstance(player, SplitVideoPlayerWidget):
                            # Для разделенного потока нужно перезагрузить конфигурацию
                            split_config = self._source_config.get(camera)
                            if split_config:
                                player.stop()
                                if player.set_split_config(split_config, new_segment):
                                    self._current_segments[camera] = new_segment
                                    self._current_segment_indices[camera] = target_segment_idx
                                else:
                                    self.logger.warning(f"Failed to switch split segment for camera {camera}: {new_segment}")
                        else:
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
    
    def _seek_player(self, player, position_ms: int):
        """Перемотать конкретный плеер на позицию"""
        if isinstance(player, SplitVideoPlayerWidget):
            player.seek(position_ms)
        elif hasattr(player, 'player') and player.player:
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
            if isinstance(player, SplitVideoPlayerWidget):
                player.set_playback_speed(speed)
            elif hasattr(player, 'player') and player.player:
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
    
    def _enter_fullscreen_mode(self, grid_idx: int):
        """Войти в полноэкранный режим для указанной ячейки"""
        if grid_idx not in self._grid_cell_widgets:
            self.logger.warning(f"Invalid grid_idx for fullscreen: {grid_idx}")
            return
        
        widget = self._grid_cell_widgets[grid_idx]
        if not widget:
            self.logger.warning(f"Widget is None for grid_idx: {grid_idx}")
            return
        
        # Сохранить текущее состояние сетки
        self._saved_grid_state = {}
        rows = self.grid_layout.rowCount()
        cols = self.grid_layout.columnCount()
        
        # Сохранить состояние всех виджетов
        for idx, w in self._grid_cell_widgets.items():
            if w:
                # Получить позицию виджета в сетке
                position = None
                for i in range(self.grid_layout.count()):
                    item = self.grid_layout.itemAt(i)
                    if item and item.widget() == w:
                        position = self.grid_layout.getItemPosition(i)
                        break
                
                if position:
                    row, col, rowspan, colspan = position
                    self._saved_grid_state[idx] = {
                        'widget': w,
                        'row': row,
                        'col': col,
                        'rowspan': rowspan,
                        'colspan': colspan,
                        'visible': w.isVisible()
                    }
        
        # Скрыть все виджеты кроме выбранного
        for idx, w in self._grid_cell_widgets.items():
            if w and idx != grid_idx:
                w.setVisible(False)
        
        # Развернуть выбранный виджет на всю сетку
        # Сначала удалить виджет из текущей позиции
        self.grid_layout.removeWidget(widget)
        
        # Добавить виджет на всю сетку
        self.grid_layout.addWidget(widget, 0, 0, rows, cols)
        widget.setVisible(True)
        
        # Установить stretch factors для того, чтобы виджет занимал всю доступную область
        for r in range(rows):
            self.grid_layout.setRowStretch(r, 1)
        for c in range(cols):
            self.grid_layout.setColumnStretch(c, 1)
        
        # Убрать ограничения размера для полноэкранного виджета
        widget.setMaximumSize(16777215, 16777215)  # Qt maximum size
        
        self._fullscreen_cell_index = grid_idx
        
        # Установить фокус для обработки клавиатуры
        self.setFocus()
        
        # Обновить layout
        self.grid_layout.update()
        
        self.logger.info(f"Entered fullscreen mode for grid_idx={grid_idx}")
    
    def _exit_fullscreen_mode(self):
        """Выйти из полноэкранного режима"""
        if self._fullscreen_cell_index is None:
            return
        
        grid_idx = self._fullscreen_cell_index
        widget = self._grid_cell_widgets.get(grid_idx)
        
        if not widget:
            self.logger.warning(f"Widget is None for grid_idx: {grid_idx}")
            self._fullscreen_cell_index = None
            self._saved_grid_state = {}
            return
        
        # Удалить виджет из текущей позиции
        self.grid_layout.removeWidget(widget)
        
        # Сбросить stretch factors
        rows = self.grid_layout.rowCount()
        cols = self.grid_layout.columnCount()
        for r in range(rows):
            self.grid_layout.setRowStretch(r, 0)
        for c in range(cols):
            self.grid_layout.setColumnStretch(c, 0)
        
        # Восстановить сохраненное состояние
        for idx, state in self._saved_grid_state.items():
            w = state['widget']
            row = state['row']
            col = state['col']
            rowspan = state['rowspan']
            colspan = state['colspan']
            visible = state['visible']
            
            # Добавить виджет обратно в исходную позицию
            self.grid_layout.addWidget(w, row, col, rowspan, colspan)
            w.setVisible(visible)
        
        # Восстановить stretch factors для обычной сетки
        # Определить, какие строки содержат split players
        rows_with_split_players = set()
        for i in range(self.grid_layout.count()):
            item = self.grid_layout.itemAt(i)
            if item and item.widget():
                try:
                    position = self.grid_layout.getItemPosition(i)
                    row, col, rowspan, colspan = position
                    if rowspan > 1:
                        for r in range(row, min(row + rowspan, rows)):
                            rows_with_split_players.add(r)
                except (AttributeError, TypeError):
                    pass
        
        # Установить stretch factors: строки с split players получают 2, остальные 1
        for r in range(rows):
            if r in rows_with_split_players:
                self.grid_layout.setRowStretch(r, 2)
            else:
                self.grid_layout.setRowStretch(r, 1)
        
        # Столбцы равномерно
        for c in range(cols):
            self.grid_layout.setColumnStretch(c, 1)
        
        self._fullscreen_cell_index = None
        self._saved_grid_state = {}
        
        # Обновить layout
        self.grid_layout.update()
        
        self.logger.info(f"Exited fullscreen mode")
    
    def keyPressEvent(self, event):
        """Обработка нажатий клавиш"""
        if event.key() == Qt.Key.Key_Escape:
            if self._fullscreen_cell_index is not None:
                self._exit_fullscreen_mode()
                event.accept()
                return
        
        super().keyPressEvent(event)


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
        filters_group = QGroupBox("Event Filters")
        filters_layout = QHBoxLayout()
        
        self.filter_checkboxes = {}
        event_types = {
            'camera_events': 'Camera Events',
            'system_events': 'System Events',
            'zone_events_entered': 'Zone Entered',
            'zone_events_left': 'Zone Left'
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
        timeline_group = QGroupBox("Timeline")
        timeline_layout = QVBoxLayout()
        
        # Верхняя строка: метки даты-времени начала и конца, текущее время в центре
        time_labels_layout = QHBoxLayout()
        
        # Метка начала (слева)
        self.start_time_label = QLabel("--")
        self.start_time_label.setStyleSheet("font-weight: bold; color: blue;")
        time_labels_layout.addWidget(self.start_time_label)
        
        time_labels_layout.addStretch()
        
        # Текущее время (в центре)
        self.current_time_label = QLabel("--")
        self.current_time_label.setStyleSheet("font-weight: bold; font-size: 12pt; color: green;")
        self.current_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_labels_layout.addWidget(self.current_time_label)
        
        time_labels_layout.addStretch()
        
        # Метка конца (справа)
        self.end_time_label = QLabel("--")
        self.end_time_label.setStyleSheet("font-weight: bold; color: blue;")
        time_labels_layout.addWidget(self.end_time_label)
        
        timeline_layout.addLayout(time_labels_layout)
        
        # Кнопки перемотки
        seek_buttons_layout = QHBoxLayout()
        seek_buttons_layout.addStretch()
        
        self.seek_back_5min_btn = QPushButton("← 5 min")
        self.seek_back_5min_btn.clicked.connect(lambda: self._seek_relative(-5 * 60 * 1000))
        seek_buttons_layout.addWidget(self.seek_back_5min_btn)
        
        self.seek_back_1min_btn = QPushButton("← 1 min")
        self.seek_back_1min_btn.clicked.connect(lambda: self._seek_relative(-1 * 60 * 1000))
        seek_buttons_layout.addWidget(self.seek_back_1min_btn)
        
        seek_buttons_layout.addStretch()
        
        self.seek_forward_1min_btn = QPushButton("1 min →")
        self.seek_forward_1min_btn.clicked.connect(lambda: self._seek_relative(1 * 60 * 1000))
        seek_buttons_layout.addWidget(self.seek_forward_1min_btn)
        
        self.seek_forward_5min_btn = QPushButton("5 min →")
        self.seek_forward_5min_btn.clicked.connect(lambda: self._seek_relative(5 * 60 * 1000))
        seek_buttons_layout.addWidget(self.seek_forward_5min_btn)
        
        seek_buttons_layout.addStretch()
        
        timeline_layout.addLayout(seek_buttons_layout)
        
        # Контейнер для слайдера и меток
        slider_container = QWidget()
        slider_layout = QVBoxLayout(slider_container)
        slider_layout.setContentsMargins(0, 0, 0, 0)
        slider_layout.setSpacing(0)
        
        # Виджет для отображения доступности записей (цветовая индикация)
        self.availability_widget = RecordingAvailabilityWidget()
        self.availability_widget.setFixedHeight(15)
        slider_layout.addWidget(self.availability_widget)
        
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
        
        # Хранить сегменты для цветовой индикации
        self._recording_segments = []  # [(start_time, end_time), ...]
        
    def set_time_range(self, start_time: datetime.datetime, end_time: datetime.datetime, recording_segments: List[Tuple] = None):
        """Установить временной диапазон"""
        self._start_time = start_time
        self._end_time = end_time
        self._recording_segments = recording_segments or []
        
        total_seconds = (end_time - start_time).total_seconds()
        self.slider.setMaximum(int(total_seconds * 1000))
        
        # Обновить метки даты-времени
        if start_time:
            self.start_time_label.setText(start_time.strftime('%Y-%m-%d %H:%M:%S'))
        if end_time:
            self.end_time_label.setText(end_time.strftime('%Y-%m-%d %H:%M:%S'))
        
        # Обновить виджет доступности записей
        if hasattr(self, 'availability_widget'):
            self.availability_widget.set_segments(self._recording_segments, start_time, end_time)
        
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
        current_str = current_time.strftime('%Y-%m-%d %H:%M:%S')
        self.current_time_label.setText(current_str)
    
    def _seek_relative(self, delta_ms: int):
        """Перемотка на указанное количество миллисекунд"""
        new_position = max(0, min(self.slider.maximum(), self._current_position_ms + delta_ms))
        self.set_position(new_position)
        self.position_changed.emit(new_position)
    
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


class RecordingAvailabilityWidget(QWidget):
    """Виджет для отображения цветовой индикации наличия записей"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments = []  # [(start_time, end_time), ...]
        self._start_time = None
        self._end_time = None
    
    def set_segments(self, segments: List[Tuple], start_time: datetime.datetime, end_time: datetime.datetime):
        """Установить сегменты записей для отображения"""
        self._segments = segments
        self._start_time = start_time
        self._end_time = end_time
        self.update()
    
    def paintEvent(self, event):
        """Отрисовать цветовую индикацию записей"""
        super().paintEvent(event)
        
        if not self._segments or not self._start_time or not self._end_time:
            return
        
        try:
            from PyQt6.QtGui import QPainter, QColor
        except ImportError:
            from PyQt5.QtGui import QPainter, QColor
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        widget_width = self.width()
        widget_height = self.height()
        total_ms = (self._end_time - self._start_time).total_seconds() * 1000
        
        if total_ms <= 0:
            painter.end()
            return
        
        # Отрисовать зеленые полосы для сегментов с записями
        for start_time, end_time in self._segments:
            start_ms = (start_time - self._start_time).total_seconds() * 1000
            end_ms = (end_time - self._start_time).total_seconds() * 1000
            
            x = int((start_ms / total_ms) * widget_width)
            w = int(((end_ms - start_ms) / total_ms) * widget_width)
            
            # Зеленая полоса для записей
            painter.fillRect(x, 0, w, widget_height, QColor(0, 255, 0, 180))
        
        painter.end()


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
        self._current_state = 'idle'  # 'idle', 'playing', 'paused'
        
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
        
        # Установить начальные стили
        self._update_button_styles()
        
        layout.addStretch()
        
        # Выбор скорости
        layout.addWidget(QLabel("Speed:"))
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
    
    def set_speed(self, speed: float):
        """Установить скорость воспроизведения программно"""
        speeds = [0.5, 1.0, 2.0, 4.0, 8.0]
        try:
            index = speeds.index(speed)
            self.speed_combo.setCurrentIndex(index)
            self._current_speed = speed
        except ValueError:
            self.logger.warning(f"Invalid speed value: {speed}, using default 1.0")
            self.speed_combo.setCurrentIndex(1)
            self._current_speed = 1.0
    
    def set_state(self, state: str):
        """Установить состояние воспроизведения и обновить стили кнопок"""
        self._current_state = state
        self._update_button_styles()
    
    def _update_button_styles(self):
        """Обновить стили кнопок в зависимости от текущего состояния"""
        # Базовый стиль для неактивных кнопок
        base_style = "QPushButton { background-color: #f0f0f0; border: 1px solid #ccc; padding: 5px 15px; }"
        active_style = "QPushButton { background-color: #4CAF50; color: white; border: 2px solid #45a049; padding: 5px 15px; font-weight: bold; }"
        
        # Сбросить все кнопки к базовому стилю
        self.play_btn.setStyleSheet(base_style)
        self.pause_btn.setStyleSheet(base_style)
        self.stop_btn.setStyleSheet(base_style)
        
        # Выделить активную кнопку
        if self._current_state == 'playing':
            self.play_btn.setStyleSheet(active_style)
        elif self._current_state == 'paused':
            self.pause_btn.setStyleSheet(active_style)
        elif self._current_state == 'idle':
            self.stop_btn.setStyleSheet(active_style)


class SplitVideoPlayerWidget(QWidget):
    """Виджет для воспроизведения разделенного потока на несколько источников"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_module_logger("split_video_player")
        
        self._video_player = None  # VideoPlayerWidget для основного потока
        self._split_config = None  # Конфигурация разделения
        self._region_widgets = []  # Виджеты для отображения областей
        self._region_pixmaps = {}  # {widget_id: pixmap} - последние pixmap для каждого виджета области
        self._current_frame = None  # Текущий кадр для разделения
        self._extraction_timer = None  # Таймер для извлечения кадров
        
        self._init_ui()
        
    def _init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
    def set_split_config(self, split_config: Dict, video_path: str):
        """Установить конфигурацию разделения и загрузить видео"""
        self.logger.info(f"SplitVideoPlayerWidget.set_split_config called with video_path={video_path}")
        self._split_config = split_config
        
        if not split_config or not split_config.get('split', False):
            self.logger.warning("Invalid split config provided")
            return False
        
        num_split = split_config.get('num_split', 0)
        src_coords = split_config.get('src_coords', [])
        source_names = split_config.get('source_names', [])
        
        self.logger.info(f"Split config: num_split={num_split}, src_coords count={len(src_coords)}, source_names={source_names}")
        
        if num_split == 0 or len(src_coords) < num_split:
            self.logger.warning(f"Invalid split config: num_split={num_split}, src_coords={len(src_coords)}")
            return False
        
        # Очистить существующие виджеты
        self._clear_regions()
        
        # Создать основной VideoPlayerWidget (скрытый, только для декодирования)
        self._video_player = VideoPlayerWidget(parent=self, logger_name="split_main")
        self._video_player.hide()  # Скрыть основной плеер
        
        # Создать виджеты для каждой области
        layout = self.layout()
        for i in range(num_split):
            # Контейнер для области
            region_container = QWidget()
            region_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            region_container.setStyleSheet("border: 2px solid #888888;")
            region_container.setMinimumSize(100, 100)  # Минимальный размер для предотвращения слишком маленьких виджетов
            region_layout = QVBoxLayout(region_container)
            region_layout.setContentsMargins(0, 0, 0, 0)
            region_layout.setSpacing(0)
            
            # Метка с именем источника
            source_name = source_names[i] if i < len(source_names) else f"Source{i}"
            label = QLabel(source_name)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("background-color: rgba(0, 0, 0, 200); color: white; padding: 3px; font-weight: bold;")
            region_layout.addWidget(label)
            
            # Виджет для отображения области
            region_widget = QLabel()
            region_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            region_widget.setStyleSheet("background-color: black;")
            region_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            
            # Добавить обработчик resizeEvent для перемасштабирования
            original_resize = region_widget.resizeEvent
            widget_id = id(region_widget)
            def on_region_resize(event, widget_id=widget_id):
                original_resize(event)
                # Перемасштабировать последний pixmap если он есть
                if widget_id in self._region_pixmaps:
                    pixmap = self._region_pixmaps[widget_id]
                    widget_size = event.size()
                    if widget_size.width() > 0 and widget_size.height() > 0:
                        scaled_pixmap = pixmap.scaled(
                            widget_size,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation
                        )
                        # Найти виджет по id
                        for region_info in self._region_widgets:
                            if id(region_info['widget']) == widget_id:
                                region_info['widget'].setPixmap(scaled_pixmap)
                                break
            
            region_widget.resizeEvent = on_region_resize
            
            # Добавить виджет в layout только если не используется внешний режим
            # (внешний режим определяется через атрибут _external_mode)
            if not getattr(self, '_external_mode', False):
                region_layout.addWidget(region_widget, stretch=1)
                layout.addWidget(region_container)
            
            self._region_widgets.append({
                'container': region_container,
                'widget': region_widget,
                'label': label,
                'coords': src_coords[i] if i < len(src_coords) else None,
                'source_name': source_name
            })
        
        # Загрузить видео в основной плеер
        if video_path and os.path.exists(video_path):
            if not os.path.isabs(video_path):
                video_path = os.path.abspath(video_path)
            
            file_size = os.path.getsize(video_path) if os.path.exists(video_path) else 0
            self.logger.info(f"Loading video for split player: path={video_path}, size={file_size} bytes")
            
            play_result = self._video_player.play_video(video_path)
            self.logger.info(f"play_video() returned: {play_result}")
            
            if play_result:
                # Подключить обработчик обновления кадров для разделения
                # Использовать таймер для периодического извлечения кадров
                self.logger.info("Video loaded successfully, setting up frame extraction")
                self._setup_frame_extraction()
                self.logger.info("Frame extraction setup completed")
                return True
            else:
                self.logger.error(f"Failed to load video: {video_path}")
                return False
        else:
            self.logger.error(f"Video file not found: {video_path}")
        
        return False
    
    def _setup_frame_extraction(self):
        """Настроить извлечение кадров для разделения"""
        self.logger.info("Setting up frame extraction")
        
        # Проверить состояние VideoPlayerWidget
        if not self._video_player:
            self.logger.error("_video_player is None, cannot setup frame extraction")
            return
        
        has_opencv = hasattr(self._video_player, '_use_opencv') and self._video_player._use_opencv
        self.logger.info(f"VideoPlayerWidget._use_opencv = {has_opencv}")
        
        # Для OpenCV - перехватывать кадры через переопределение метода обновления
        if has_opencv:
            # Сохранить оригинальный метод обновления кадра
            if hasattr(self._video_player, '_update_frame_opencv'):
                self.logger.info("Found _update_frame_opencv method, creating wrapper")
                # Создать обертку для перехвата кадров
                original_update = self._video_player._update_frame_opencv
                
                def wrapped_update():
                    # Вызвать оригинальный метод
                    self.logger.info("wrapped_update() called - calling original_update()")
                    original_update()
                    # Извлечь кадр для разделения (кадр уже прочитан в оригинальном методе)
                    self.logger.info("wrapped_update() - calling _extract_current_frame()")
                    self._extract_current_frame()
                
                # ВАЖНО: Переподключить таймер к новому wrapper методу
                # Таймер был подключен к старому методу, нужно переподключить
                if hasattr(self._video_player, 'timer') and self._video_player.timer:
                    self.logger.info("Reconnecting timer to wrapped_update method")
                    self._video_player.timer.timeout.disconnect()  # Отключить старое подключение
                    self._video_player._update_frame_opencv = wrapped_update  # Установить новый метод
                    self._video_player.timer.timeout.connect(wrapped_update)  # Подключить к wrapper
                    self.logger.info(f"Timer reconnected. timer.isActive: {self._video_player.timer.isActive()}")
                else:
                    # Если таймера нет, просто заменить метод
                    self._video_player._update_frame_opencv = wrapped_update
                    self.logger.info("Wrapper installed (no timer to reconnect)")
                self._extraction_timer = None  # Не нужен отдельный таймер
                self.logger.info("Frame extraction wrapper created successfully")
            else:
                self.logger.warning("_update_frame_opencv method not found, using fallback timer")
                # Fallback: использовать таймер
                try:
                    from PyQt6.QtCore import QTimer
                except ImportError:
                    from PyQt5.QtCore import QTimer
                
                self._extraction_timer = QTimer()
                self._extraction_timer.timeout.connect(self._update_split_frames_opencv)
                
                if hasattr(self._video_player, 'timer') and self._video_player.timer:
                    interval = self._video_player.timer.interval()
                    self._extraction_timer.start(interval)
                    self.logger.info(f"Extraction timer started with interval {interval}ms")
                else:
                    self.logger.warning("VideoPlayerWidget timer not found, extraction timer not started")
        else:
            # QMediaPlayer режим - использовать QVideoSink для перехвата кадров
            # Пока используем только OpenCV режим
            self.logger.warning("QMediaPlayer mode - frame extraction may not work correctly")
            self._extraction_timer = None
    
    def _extract_current_frame(self):
        """Извлечь текущий кадр из VideoPlayerWidget для разделения"""
        self.logger.info("_extract_current_frame() called")
        if not self._video_player:
            self.logger.warning("_extract_current_frame: _video_player is None")
            return
        
        frame = None
        
        # Попытаться получить сохраненный кадр из VideoPlayerWidget
        if hasattr(self._video_player, '_current_frame') and self._video_player._current_frame is not None:
            frame = self._video_player._current_frame.copy()
            self.logger.info(f"_extract_current_frame: Got frame from _current_frame, size={frame.shape if frame is not None else None}")
        else:
            self.logger.debug("_extract_current_frame: _current_frame is None or not available")
        
        # Fallback: прочитать кадр напрямую из cap если _current_frame недоступен
        if frame is None and hasattr(self._video_player, 'cap') and self._video_player.cap:
            cap = self._video_player.cap
            if cap.isOpened():
                # Сохранить текущую позицию кадра
                current_pos = cap.get(cv2.CAP_PROP_POS_FRAMES)
                ret, frame = cap.read()
                if ret and frame is not None:
                    self.logger.debug(f"_extract_current_frame: Read frame from cap, size={frame.shape}")
                    # Вернуть позицию обратно (кадр уже был прочитан в _update_frame_opencv)
                    # Но для разделения нам нужен текущий кадр, поэтому оставляем позицию как есть
                    pass
                else:
                    self.logger.debug(f"_extract_current_frame: Failed to read frame from cap, ret={ret}")
                    # Если не удалось прочитать, вернуть позицию
                    cap.set(cv2.CAP_PROP_POS_FRAMES, current_pos)
            else:
                self.logger.debug("_extract_current_frame: cap is not opened")
        else:
            if not hasattr(self._video_player, 'cap'):
                self.logger.debug("_extract_current_frame: _video_player has no cap attribute")
            elif not self._video_player.cap:
                self.logger.debug("_extract_current_frame: _video_player.cap is None")
        
        # Разделить кадр на области если он доступен
        if frame is not None:
            self.logger.info(f"_extract_current_frame: Calling _split_frame with frame size={frame.shape}")
            self._split_frame(frame)
        else:
            self.logger.warning("_extract_current_frame: Frame is None, cannot split")
    
    def _update_split_frames_opencv(self):
        """Обновить разделенные кадры для OpenCV режима"""
        if not self._video_player or not hasattr(self._video_player, 'cap'):
            self.logger.debug("_update_split_frames_opencv: _video_player or cap not available")
            return
        
        cap = self._video_player.cap
        if not cap or not cap.isOpened():
            self.logger.debug(f"_update_split_frames_opencv: cap is None or not opened. cap={cap}, isOpened={cap.isOpened() if cap else False}")
            return
        
        # Попытаться получить сохраненный кадр из VideoPlayerWidget
        frame = None
        if hasattr(self._video_player, '_current_frame') and self._video_player._current_frame is not None:
            frame = self._video_player._current_frame.copy()
            self.logger.debug(f"_update_split_frames_opencv: Got frame from _current_frame, size={frame.shape if frame is not None else None}")
        
        # Fallback: прочитать кадр напрямую из cap
        if frame is None:
            ret, frame = cap.read()
            if not ret or frame is None:
                self.logger.debug(f"_update_split_frames_opencv: Failed to read frame from cap, ret={ret}")
                return
            self.logger.debug(f"_update_split_frames_opencv: Read frame from cap, size={frame.shape}")
        
        # Разделить кадр на области
        if frame is not None:
            self.logger.debug(f"_update_split_frames_opencv: Calling _split_frame with frame size={frame.shape}")
            self._split_frame(frame)
        else:
            self.logger.debug("_update_split_frames_opencv: Frame is None, cannot split")
    
    def _split_frame(self, frame):
        """Разделить кадр на области согласно конфигурации"""
        self.logger.info(f"_split_frame() called with frame shape={frame.shape if frame is not None else None}")
        if not self._split_config or not self._region_widgets:
            self.logger.warning(f"_split_frame: Missing config or widgets. config={self._split_config is not None}, widgets={len(self._region_widgets) if self._region_widgets else 0}")
            return
        
        if cv2 is None:
            self.logger.error("OpenCV not available for frame splitting")
            return
        
        try:
            self.logger.info(f"_split_frame: Processing frame with shape={frame.shape}, num_regions={len(self._region_widgets)}")
            
            # Конвертировать в RGB если нужно
            if len(frame.shape) == 3 and frame.shape[2] == 3:
                # BGR to RGB для отображения
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            else:
                frame_rgb = frame
            
            # Разделить на области
            for idx, region_info in enumerate(self._region_widgets):
                coords = region_info['coords']
                source_name = region_info.get('source_name', f'region_{idx}')
                
                if not coords or len(coords) < 4:
                    self.logger.warning(f"_split_frame: Region {idx} ({source_name}) has invalid coords: {coords}")
                    continue
                
                x, y, w, h = int(coords[0]), int(coords[1]), int(coords[2]), int(coords[3])
                self.logger.info(f"_split_frame: Extracting region {idx} ({source_name}) at x={x}, y={y}, w={w}, h={h}")
                self.logger.debug(f"_split_frame: Region {idx} ({source_name}) coords: x={x}, y={y}, w={w}, h={h}")
                
                # Проверить границы
                frame_h, frame_w = frame_rgb.shape[:2]
                x = max(0, min(x, frame_w))
                y = max(0, min(y, frame_h))
                w = min(w, frame_w - x)
                h = min(h, frame_h - y)
                
                if w <= 0 or h <= 0:
                    self.logger.warning(f"_split_frame: Region {idx} ({source_name}) has invalid dimensions after clipping: w={w}, h={h}")
                    continue
                
                # Извлечь область
                region = frame_rgb[y:y+h, x:x+w].copy()
                self.logger.debug(f"_split_frame: Extracted region {idx} ({source_name}) with shape={region.shape}")
                
                # Отобразить в виджете
                self._display_region(region_info['widget'], region, source_name)
                
        except Exception as e:
            self.logger.error(f"Error splitting frame: {e}", exc_info=True)
    
    def _display_region(self, widget: QLabel, region, source_name: str = "unknown"):
        """Отобразить область в виджете"""
        self.logger.info(f"_display_region() called for {source_name}: region shape={region.shape if region is not None else None}, widget size={widget.size().width()}x{widget.size().height()}")
        try:
            from PyQt6.QtGui import QImage, QPixmap
        except ImportError:
            from PyQt5.QtGui import QImage, QPixmap
        
        h, w, ch = region.shape
        bytes_per_line = ch * w
        
        q_image = QImage(region.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)
        
        # Сохранить оригинальный pixmap для перемасштабирования при изменении размера
        widget_id = id(widget)
        self._region_pixmaps[widget_id] = pixmap
        
        # Масштабировать под размер виджета
        widget_size = widget.size()
        if widget_size.width() > 0 and widget_size.height() > 0:
            scaled_pixmap = pixmap.scaled(
                widget_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            widget.setPixmap(scaled_pixmap)
            self.logger.info(f"_display_region ({source_name}): Pixmap set successfully, scaled size={scaled_pixmap.size().width()}x{scaled_pixmap.size().height()}")
        else:
            self.logger.warning(f"_display_region ({source_name}): Widget size is invalid: {widget_size.width()}x{widget_size.height()}, cannot scale pixmap")
    
    def _clear_regions(self):
        """Очистить виджеты областей"""
        if self._extraction_timer:
            self._extraction_timer.stop()
            self._extraction_timer.deleteLater()
            self._extraction_timer = None
        
        # Очистить сохраненные pixmap
        self._region_pixmaps = {}
        
        layout = self.layout()
        if layout:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        
        if self._video_player:
            self._video_player.stop()
            self._video_player.deleteLater()
            self._video_player = None
        
        self._region_widgets.clear()
    
    def play(self):
        """Запустить воспроизведение"""
        self.logger.info("SplitVideoPlayerWidget.play() called")
        
        if not self._video_player:
            self.logger.error("play(): _video_player is None")
            return
        
        self.logger.info(f"play(): _video_player exists, _is_playing={getattr(self._video_player, '_is_playing', 'unknown')}")
        
        if hasattr(self._video_player, 'player') and self._video_player.player:
            self.logger.info("play(): Using QMediaPlayer")
            if pyqt_version == 6:
                self._video_player.player.play()
            else:
                self._video_player.player.play()
            self.logger.info("play(): QMediaPlayer.play() called")
        elif hasattr(self._video_player, 'timer') and self._video_player.timer:
            self.logger.info("play(): Using OpenCV timer")
            if not self._video_player.timer.isActive():
                self._video_player.timer.start()
                self.logger.info("play(): VideoPlayerWidget timer started")
            else:
                self.logger.info("play(): VideoPlayerWidget timer already active")
        else:
            self.logger.warning("play(): No player or timer found in _video_player")
            if hasattr(self._video_player, 'cap'):
                self.logger.info(f"play(): _video_player.cap exists: {self._video_player.cap is not None}")
                if self._video_player.cap:
                    self.logger.info(f"play(): cap.isOpened() = {self._video_player.cap.isOpened()}")
        
        # Запустить таймер извлечения кадров если есть
        if self._extraction_timer:
            if not self._extraction_timer.isActive():
                self._extraction_timer.start()
                self.logger.info("play(): Extraction timer started")
            else:
                self.logger.info("play(): Extraction timer already active")
        else:
            self.logger.info("play(): No extraction timer (using wrapper method)")
    
    def pause(self):
        """Приостановить воспроизведение"""
        if self._video_player:
            if hasattr(self._video_player, 'player') and self._video_player.player:
                try:
                    if pyqt_version == 6:
                        from PyQt6.QtMultimedia import QMediaPlayer
                        if self._video_player.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                            self._video_player.player.pause()
                    else:
                        from PyQt5.QtMultimedia import QMediaPlayer
                        if self._video_player.player.state() == QMediaPlayer.PlayingState:
                            self._video_player.player.pause()
                except Exception:
                    pass
            elif hasattr(self._video_player, 'timer') and self._video_player.timer:
                if self._video_player.timer.isActive():
                    self._video_player.timer.stop()
            
            # Остановить таймер извлечения кадров
            if self._extraction_timer and self._extraction_timer.isActive():
                self._extraction_timer.stop()
    
    def stop(self):
        """Остановить воспроизведение"""
        if self._extraction_timer:
            self._extraction_timer.stop()
        if self._video_player:
            self._video_player.stop()
    
    def seek(self, position_ms: int):
        """Перемотать на позицию"""
        if self._video_player:
            if hasattr(self._video_player, 'player') and self._video_player.player:
                if pyqt_version == 6:
                    self._video_player.player.setPosition(position_ms)
                else:
                    self._video_player.player.setPosition(position_ms)
            elif hasattr(self._video_player, 'cap') and self._video_player.cap:
                import cv2
                fps = self._video_player.cap.get(cv2.CAP_PROP_FPS) or 30
                frame_number = int((position_ms / 1000.0) * fps)
                self._video_player.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    
    def set_playback_speed(self, speed: float):
        """Установить скорость воспроизведения"""
        if self._video_player:
            if hasattr(self._video_player, 'player') and self._video_player.player:
                try:
                    if pyqt_version == 6:
                        self._video_player.player.setPlaybackRate(speed)
                    else:
                        self._video_player.player.setPlaybackRate(speed)
                except Exception:
                    pass
            elif hasattr(self._video_player, 'timer') and self._video_player.timer:
                if hasattr(self._video_player, 'cap') and self._video_player.cap:
                    import cv2
                    fps = self._video_player.cap.get(cv2.CAP_PROP_FPS) or 30
                    base_interval = int(1000 / fps)
                    new_interval = int(base_interval / speed)
                    if new_interval > 0:
                        self._video_player.timer.setInterval(new_interval)
