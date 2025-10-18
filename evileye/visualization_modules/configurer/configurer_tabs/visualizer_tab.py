import copy
import json
import os.path
try:
    from PyQt6 import QtGui
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
        QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem,
        QMenu, QMainWindow, QApplication, QCheckBox, QPushButton, QTabWidget,
        QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
        QFileDialog, QSpinBox, QDoubleSpinBox, QTextEdit, QSplitter, QColorDialog
    )
    from PyQt6.QtGui import QIcon, QColor, QFont
    from PyQt6.QtGui import QAction
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 6
except ImportError:
    from PyQt5 import QtGui
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
        QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem,
        QMenu, QMainWindow, QApplication, QCheckBox, QPushButton, QTabWidget,
        QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
        QFileDialog, QSpinBox, QDoubleSpinBox, QTextEdit, QSplitter, QColorDialog
    )
    from PyQt5.QtGui import QIcon, QColor, QFont
    from PyQt5.QtWidgets import QAction
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 5
from evileye.utils import utils
import sys
from evileye.capture.video_capture_base import CaptureDeviceType
from evileye.capture import VideoCaptureOpencv
from evileye.visualization_modules.configurer import parameters_processing
from evileye.visualization_modules.configurer.configurer_tabs.base_tab import BaseTab
from evileye.visualization_modules.configurer.validators import (
    ValidatedLineEdit, ValidatedSpinBox, ValidatedDoubleSpinBox, 
    ValidatedCheckBox, ValidatedComboBox, Validators
)


class VisualizerTab(BaseTab):
    def __init__(self, config_params, parent=None):
        super().__init__(config_params, parent)

        self.params = config_params
        self.default_src_params = self.params.get('visualizer', {})
        self.config_result = copy.deepcopy(config_params)

        self.proj_root = utils.get_project_root()
        self.hor_layouts = {}
        self.split_check_boxes = []
        self.botsort_check_boxes = []
        self.coords_edits = []
        self.src_counter = 0

        self.line_edit_param = {}  # Словарь для сопоставления полей интерфейса с полями json-файла

        # Используем main_layout из BaseTab вместо создания нового
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._setup_layout()

    def _setup_layout(self):
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        # Основные параметры визуализатора
        self._setup_basic_visualizer_section()
        
        # Текстовые настройки
        self._setup_text_settings_section()
        
        # Event signalization
        self._setup_event_signalization_section()
        
        # Attributes display
        self._setup_attributes_display_section()
        
        # Layout settings
        self._setup_layout_settings_section()

    def _setup_basic_visualizer_section(self):
        """Настройка основных параметров визуализатора"""
        layout = self.create_form_layout()
        group_box = self.add_group_box("Основные параметры визуализатора", layout)
        layout = self.create_form_layout()
        
        # Количество камер по ширине
        self.num_width = ValidatedSpinBox()
        self.num_width.setRange(1, 10)
        self.num_width.setValue(self.default_src_params.get('num_width', 2))
        self.num_width.setToolTip("Количество камер по горизонтали")
        self.add_validated_widget("Number of cameras in width", self.num_width, Validators.POSITIVE_INT)
        
        # Количество камер по высоте
        self.num_height = ValidatedSpinBox()
        self.num_height.setRange(1, 10)
        self.num_height.setValue(self.default_src_params.get('num_height', 2))
        self.num_height.setToolTip("Количество камер по вертикали")
        self.add_validated_widget("Number of cameras in height", self.num_height, Validators.POSITIVE_INT)
        
        # Размер буфера визуализации
        self.visual_buffer_num_frames = ValidatedSpinBox()
        self.visual_buffer_num_frames.setRange(1, 1000)
        self.visual_buffer_num_frames.setValue(self.default_src_params.get('visual_buffer_num_frames', 10))
        self.visual_buffer_num_frames.setToolTip("Размер буфера кадров для визуализации")
        self.add_validated_widget("Visual buffer size", self.visual_buffer_num_frames, Validators.POSITIVE_INT)
        
        # ID источников для визуализации
        self.source_ids = ValidatedLineEdit()
        source_ids_value = self.default_src_params.get('source_ids', [])
        self.source_ids.setText(str(source_ids_value) if source_ids_value else '[]')
        self.source_ids.setToolTip("Список ID источников для визуализации (например: [0, 1, 2])")
        self.add_validated_widget("Visualized sources", self.source_ids, Validators.SOURCE_IDS)
        
        # FPS источников
        self.fps = ValidatedLineEdit()
        fps_value = self.default_src_params.get('fps', [])
        self.fps.setText(str(fps_value) if fps_value else '[]')
        self.fps.setToolTip("FPS для каждого источника (например: [30, 25, 30])")
        self.add_validated_widget("Sources fps", self.fps, Validators.SOURCE_IDS)
        
        # GUI включен
        self.gui_enabled = ValidatedCheckBox("GUI Enabled")
        self.gui_enabled.setChecked(self.default_src_params.get('gui_enabled', True))
        self.gui_enabled.setToolTip("Включить графический интерфейс")
        layout.addWidget(self.gui_enabled)
        
        # Показывать отладочную информацию
        self.show_debug_info = ValidatedCheckBox("Show debug information")
        self.show_debug_info.setChecked(self.default_src_params.get('show_debug_info', False))
        self.show_debug_info.setToolTip("Показывать отладочную информацию на видео")
        layout.addWidget(self.show_debug_info)
        
        # Журнал объектов включен
        self.objects_journal_enabled = ValidatedCheckBox("Objects journal enabled")
        self.objects_journal_enabled.setChecked(self.default_src_params.get('objects_journal_enabled', True))
        self.objects_journal_enabled.setToolTip("Включить журнал объектов")
        layout.addWidget(self.objects_journal_enabled)
        
        self.main_layout.addWidget(group_box)

    def _setup_text_settings_section(self):
        """Настройка текстовых параметров"""
        layout = self.create_form_layout()
        group_box = self.add_group_box("Текстовые настройки", layout)
        layout = self.create_form_layout()
        
        # Масштаб шрифта
        self.font_scale = ValidatedDoubleSpinBox()
        self.font_scale.setRange(0.1, 5.0)
        self.font_scale.setSingleStep(0.1)
        self.font_scale.setValue(self.default_src_params.get('font_scale', 0.7))
        self.font_scale.setToolTip("Масштаб шрифта для текста на видео")
        self.add_validated_widget("Font scale", self.font_scale, Validators.POSITIVE_INT)
        
        # Толщина шрифта
        self.font_thickness = ValidatedSpinBox()
        self.font_thickness.setRange(1, 10)
        self.font_thickness.setValue(self.default_src_params.get('font_thickness', 2))
        self.font_thickness.setToolTip("Толщина шрифта")
        self.add_validated_widget("Font thickness", self.font_thickness, Validators.POSITIVE_INT)
        
        # Цвет текста
        self.text_color = QPushButton("Выбрать цвет")
        self.text_color.clicked.connect(self._select_text_color)
        self.text_color.setToolTip("Цвет текста на видео")
        layout.addRow("Text color", self.text_color)
        
        # Цвет фона текста
        self.text_background_color = QPushButton("Выбрать цвет")
        self.text_background_color.clicked.connect(self._select_text_background_color)
        self.text_background_color.setToolTip("Цвет фона текста")
        layout.addRow("Text background color", self.text_background_color)
        
        # Показывать ID объектов
        self.show_object_ids = ValidatedCheckBox("Show object IDs")
        self.show_object_ids.setChecked(self.default_src_params.get('show_object_ids', True))
        self.show_object_ids.setToolTip("Показывать ID объектов на видео")
        layout.addWidget(self.show_object_ids)
        
        # Показывать классы объектов
        self.show_object_classes = ValidatedCheckBox("Show object classes")
        self.show_object_classes.setChecked(self.default_src_params.get('show_object_classes', True))
        self.show_object_classes.setToolTip("Показывать классы объектов на видео")
        layout.addWidget(self.show_object_classes)
        
        # Показывать confidence
        self.show_confidence = ValidatedCheckBox("Show confidence scores")
        self.show_confidence.setChecked(self.default_src_params.get('show_confidence', True))
        self.show_confidence.setToolTip("Показывать confidence scores объектов")
        layout.addWidget(self.show_confidence)
        
        self.main_layout.addWidget(group_box)

    def _setup_event_signalization_section(self):
        """Настройка сигнализации событий"""
        layout = self.create_form_layout()
        group_box = self.add_group_box("Сигнализация событий", layout)
        layout = self.create_form_layout()
        
        # Включить сигнализацию событий
        self.event_signal_enabled = ValidatedCheckBox("Enable event signalization")
        self.event_signal_enabled.setChecked(self.default_src_params.get('event_signal_enabled', True))
        self.event_signal_enabled.setToolTip("Включить визуальную сигнализацию событий")
        self.event_signal_enabled.toggled.connect(self._on_event_signal_toggled)
        layout.addWidget(self.event_signal_enabled)
        
        # Цвет сигнализации событий
        self.event_signal_color = QPushButton("Выбрать цвет")
        self.event_signal_color.clicked.connect(self._select_event_signal_color)
        self.event_signal_color.setToolTip("Цвет сигнализации событий")
        layout.addRow("Event signal color", self.event_signal_color)
        
        # Длительность сигнализации
        self.event_signal_duration = ValidatedSpinBox()
        self.event_signal_duration.setRange(1, 60)
        self.event_signal_duration.setValue(self.default_src_params.get('event_signal_duration', 3))
        self.event_signal_duration.setToolTip("Длительность сигнализации события в секундах")
        self.add_validated_widget("Event signal duration", self.event_signal_duration, Validators.POSITIVE_INT)
        
        # Размер сигнализации
        self.event_signal_size = ValidatedSpinBox()
        self.event_signal_size.setRange(1, 50)
        self.event_signal_size.setValue(self.default_src_params.get('event_signal_size', 10))
        self.event_signal_size.setToolTip("Размер сигнализации события")
        self.add_validated_widget("Event signal size", self.event_signal_size, Validators.POSITIVE_INT)
        
        # Показывать текст событий
        self.show_event_text = ValidatedCheckBox("Show event text")
        self.show_event_text.setChecked(self.default_src_params.get('show_event_text', True))
        self.show_event_text.setToolTip("Показывать текст события на видео")
        layout.addWidget(self.show_event_text)
        
        self.main_layout.addWidget(group_box)
        
        # Инициализация состояния
        self._on_event_signal_toggled(self.event_signal_enabled.isChecked())

    def _setup_attributes_display_section(self):
        """Настройка отображения атрибутов"""
        layout = self.create_form_layout()
        group_box = self.add_group_box("Отображение атрибутов", layout)
        layout = self.create_form_layout()
        
        # Включить отображение атрибутов
        self.show_attributes = ValidatedCheckBox("Show object attributes")
        self.show_attributes.setChecked(self.default_src_params.get('show_attributes', False))
        self.show_attributes.setToolTip("Показывать атрибуты объектов на видео")
        self.show_attributes.toggled.connect(self._on_attributes_display_toggled)
        layout.addWidget(self.show_attributes)
        
        # Максимальное количество атрибутов
        self.max_attributes_display = ValidatedSpinBox()
        self.max_attributes_display.setRange(1, 20)
        self.max_attributes_display.setValue(self.default_src_params.get('max_attributes_display', 5))
        self.max_attributes_display.setToolTip("Максимальное количество атрибутов для отображения")
        self.add_validated_widget("Max attributes to display", self.max_attributes_display, Validators.POSITIVE_INT)
        
        # Показывать только важные атрибуты
        self.show_important_attributes_only = ValidatedCheckBox("Show important attributes only")
        self.show_important_attributes_only.setChecked(self.default_src_params.get('show_important_attributes_only', True))
        self.show_important_attributes_only.setToolTip("Показывать только важные атрибуты")
        layout.addWidget(self.show_important_attributes_only)
        
        # Фильтр атрибутов
        self.attributes_filter = ValidatedLineEdit()
        self.attributes_filter.setPlaceholderText("age,gender,clothing")
        self.attributes_filter.setToolTip("Список атрибутов для отображения (через запятую)")
        self.add_validated_widget("Attributes filter", self.attributes_filter, Validators.SOURCE_IDS)
        
        self.main_layout.addWidget(group_box)
        
        # Инициализация состояния
        self._on_attributes_display_toggled(self.show_attributes.isChecked())

    def _setup_layout_settings_section(self):
        """Настройка параметров компоновки"""
        layout = self.create_form_layout()
        group_box = self.add_group_box("Настройки компоновки", layout)
        layout = self.create_form_layout()
        
        # Автоматическое изменение размера
        self.auto_resize = ValidatedCheckBox("Auto resize windows")
        self.auto_resize.setChecked(self.default_src_params.get('auto_resize', True))
        self.auto_resize.setToolTip("Автоматически изменять размер окон")
        layout.addWidget(self.auto_resize)
        
        # Полноэкранный режим
        self.fullscreen = ValidatedCheckBox("Fullscreen mode")
        self.fullscreen.setChecked(self.default_src_params.get('fullscreen', False))
        self.fullscreen.setToolTip("Запуск в полноэкранном режиме")
        layout.addWidget(self.fullscreen)
        
        # Показывать сетку
        self.show_grid = ValidatedCheckBox("Show grid")
        self.show_grid.setChecked(self.default_src_params.get('show_grid', False))
        self.show_grid.setToolTip("Показывать сетку между камерами")
        layout.addWidget(self.show_grid)
        
        # Цвет сетки
        self.grid_color = QPushButton("Выбрать цвет")
        self.grid_color.clicked.connect(self._select_grid_color)
        self.grid_color.setToolTip("Цвет сетки")
        layout.addRow("Grid color", self.grid_color)
        
        # Толщина сетки
        self.grid_thickness = ValidatedSpinBox()
        self.grid_thickness.setRange(1, 10)
        self.grid_thickness.setValue(self.default_src_params.get('grid_thickness', 1))
        self.grid_thickness.setToolTip("Толщина линий сетки")
        self.add_validated_widget("Grid thickness", self.grid_thickness, Validators.POSITIVE_INT)
        
        self.main_layout.addWidget(group_box)

    def get_forms(self) -> list[QFormLayout]:
        form_layouts = []
        forms = [form for i in range(self.vertical_layout.count()) if isinstance(form := self.vertical_layout.itemAt(i), QFormLayout)]
        form_layouts.extend(forms)
        return form_layouts

    def get_params(self):
        """Получить все параметры Visualizer Tab"""
        return {
            'basic_visualizer': self._get_basic_visualizer_params(),
            'text_settings': self._get_text_settings_params(),
            'event_signalization': self._get_event_signalization_params(),
            'attributes_display': self._get_attributes_display_params(),
            'layout_settings': self._get_layout_settings_params()
        }

    def _get_basic_visualizer_params(self):
        """Получить основные параметры визуализатора"""
        return {
            'num_width': self.num_width.value(),
            'num_height': self.num_height.value(),
            'visual_buffer_num_frames': self.visual_buffer_num_frames.value(),
            'source_ids': parameters_processing.process_numeric_lists(self.source_ids.text()),
            'fps': parameters_processing.process_numeric_lists(self.fps.text()),
            'gui_enabled': self.gui_enabled.isChecked(),
            'show_debug_info': self.show_debug_info.isChecked(),
            'objects_journal_enabled': self.objects_journal_enabled.isChecked()
        }

    def _get_text_settings_params(self):
        """Получить параметры текстовых настроек"""
        return {
            'font_scale': self.font_scale.value(),
            'font_thickness': self.font_thickness.value(),
            'text_color': getattr(self, '_text_color', [255, 255, 255]),
            'text_background_color': getattr(self, '_text_background_color', [0, 0, 0]),
            'show_object_ids': self.show_object_ids.isChecked(),
            'show_object_classes': self.show_object_classes.isChecked(),
            'show_confidence': self.show_confidence.isChecked()
        }

    def _get_event_signalization_params(self):
        """Получить параметры сигнализации событий"""
        return {
            'event_signal_enabled': self.event_signal_enabled.isChecked(),
            'event_signal_color': getattr(self, '_event_signal_color', [0, 0, 255]),
            'event_signal_duration': self.event_signal_duration.value(),
            'event_signal_size': self.event_signal_size.value(),
            'show_event_text': self.show_event_text.isChecked()
        }

    def _get_attributes_display_params(self):
        """Получить параметры отображения атрибутов"""
        attributes_filter = self.attributes_filter.text().strip()
        filter_list = [item.strip() for item in attributes_filter.split(',') if item.strip()] if attributes_filter else []
        
        return {
            'show_attributes': self.show_attributes.isChecked(),
            'max_attributes_display': self.max_attributes_display.value(),
            'show_important_attributes_only': self.show_important_attributes_only.isChecked(),
            'attributes_filter': filter_list
        }

    def _get_layout_settings_params(self):
        """Получить параметры настроек компоновки"""
        return {
            'auto_resize': self.auto_resize.isChecked(),
            'fullscreen': self.fullscreen.isChecked(),
            'show_grid': self.show_grid.isChecked(),
            'grid_color': getattr(self, '_grid_color', [128, 128, 128]),
            'grid_thickness': self.grid_thickness.value()
        }

    def _on_event_signal_toggled(self, checked):
        """Обработка переключения сигнализации событий"""
        self.event_signal_color.setEnabled(checked)
        self.event_signal_duration.setEnabled(checked)
        self.event_signal_size.setEnabled(checked)
        self.show_event_text.setEnabled(checked)

    def _on_attributes_display_toggled(self, checked):
        """Обработка переключения отображения атрибутов"""
        self.max_attributes_display.setEnabled(checked)
        self.show_important_attributes_only.setEnabled(checked)
        self.attributes_filter.setEnabled(checked)

    def _select_text_color(self):
        """Выбор цвета текста"""
        color = QColorDialog.getColor()
        if color.isValid():
            self._text_color = [color.red(), color.green(), color.blue()]
            self.text_color.setStyleSheet(f"background-color: {color.name()}")

    def _select_text_background_color(self):
        """Выбор цвета фона текста"""
        color = QColorDialog.getColor()
        if color.isValid():
            self._text_background_color = [color.red(), color.green(), color.blue()]
            self.text_background_color.setStyleSheet(f"background-color: {color.name()}")

    def _select_event_signal_color(self):
        """Выбор цвета сигнализации событий"""
        color = QColorDialog.getColor()
        if color.isValid():
            self._event_signal_color = [color.red(), color.green(), color.blue()]
            self.event_signal_color.setStyleSheet(f"background-color: {color.name()}")

    def _select_grid_color(self):
        """Выбор цвета сетки"""
        color = QColorDialog.getColor()
        if color.isValid():
            self._grid_color = [color.red(), color.green(), color.blue()]
            self.grid_color.setStyleSheet(f"background-color: {color.name()}")

    def _update_ui_from_params(self):
        """Обновить UI из параметров конфигурации"""
        if not self.params:
            return
        
        # Обновляем основные параметры
        basic_params = self.params.get('basic_visualizer', {})
        if 'num_width' in basic_params:
            self.num_width.setValue(basic_params['num_width'])
        if 'num_height' in basic_params:
            self.num_height.setValue(basic_params['num_height'])
        if 'visual_buffer_num_frames' in basic_params:
            self.visual_buffer_num_frames.setValue(basic_params['visual_buffer_num_frames'])
        if 'source_ids' in basic_params:
            self.source_ids.setText(str(basic_params['source_ids']))
        if 'fps' in basic_params:
            self.fps.setText(str(basic_params['fps']))
        if 'gui_enabled' in basic_params:
            self.gui_enabled.setChecked(basic_params['gui_enabled'])
        if 'show_debug_info' in basic_params:
            self.show_debug_info.setChecked(basic_params['show_debug_info'])
        if 'objects_journal_enabled' in basic_params:
            self.objects_journal_enabled.setChecked(basic_params['objects_journal_enabled'])
        
        # Обновляем текстовые настройки
        text_params = self.params.get('text_settings', {})
        if 'font_scale' in text_params:
            self.font_scale.setValue(text_params['font_scale'])
        if 'font_thickness' in text_params:
            self.font_thickness.setValue(text_params['font_thickness'])
        if 'text_color' in text_params:
            self._text_color = text_params['text_color']
            color = QColor(*text_params['text_color'])
            self.text_color.setStyleSheet(f"background-color: {color.name()}")
        if 'text_background_color' in text_params:
            self._text_background_color = text_params['text_background_color']
            color = QColor(*text_params['text_background_color'])
            self.text_background_color.setStyleSheet(f"background-color: {color.name()}")
        if 'show_object_ids' in text_params:
            self.show_object_ids.setChecked(text_params['show_object_ids'])
        if 'show_object_classes' in text_params:
            self.show_object_classes.setChecked(text_params['show_object_classes'])
        if 'show_confidence' in text_params:
            self.show_confidence.setChecked(text_params['show_confidence'])
        
        # Обновляем сигнализацию событий
        event_params = self.params.get('event_signalization', {})
        if 'event_signal_enabled' in event_params:
            self.event_signal_enabled.setChecked(event_params['event_signal_enabled'])
        if 'event_signal_color' in event_params:
            self._event_signal_color = event_params['event_signal_color']
            color = QColor(*event_params['event_signal_color'])
            self.event_signal_color.setStyleSheet(f"background-color: {color.name()}")
        if 'event_signal_duration' in event_params:
            self.event_signal_duration.setValue(event_params['event_signal_duration'])
        if 'event_signal_size' in event_params:
            self.event_signal_size.setValue(event_params['event_signal_size'])
        if 'show_event_text' in event_params:
            self.show_event_text.setChecked(event_params['show_event_text'])
        
        # Обновляем отображение атрибутов
        attr_params = self.params.get('attributes_display', {})
        if 'show_attributes' in attr_params:
            self.show_attributes.setChecked(attr_params['show_attributes'])
        if 'max_attributes_display' in attr_params:
            self.max_attributes_display.setValue(attr_params['max_attributes_display'])
        if 'show_important_attributes_only' in attr_params:
            self.show_important_attributes_only.setChecked(attr_params['show_important_attributes_only'])
        if 'attributes_filter' in attr_params:
            self.attributes_filter.setText(','.join(attr_params['attributes_filter']))
        
        # Обновляем настройки компоновки
        layout_params = self.params.get('layout_settings', {})
        if 'auto_resize' in layout_params:
            self.auto_resize.setChecked(layout_params['auto_resize'])
        if 'fullscreen' in layout_params:
            self.fullscreen.setChecked(layout_params['fullscreen'])
        if 'show_grid' in layout_params:
            self.show_grid.setChecked(layout_params['show_grid'])
        if 'grid_color' in layout_params:
            self._grid_color = layout_params['grid_color']
            color = QColor(*layout_params['grid_color'])
            self.grid_color.setStyleSheet(f"background-color: {color.name()}")
        if 'grid_thickness' in layout_params:
            self.grid_thickness.setValue(layout_params['grid_thickness'])
