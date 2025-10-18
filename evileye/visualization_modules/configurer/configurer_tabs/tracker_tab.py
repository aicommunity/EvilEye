import copy
import json
import os.path
from ....core.logger import get_module_logger
try:
    from PyQt6 import QtGui
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
        QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem,
        QMenu, QMainWindow, QApplication, QCheckBox, QPushButton, QTabWidget,
        QGroupBox, QSpinBox, QDoubleSpinBox, QTextEdit, QFileDialog, QMessageBox
    )
    from PyQt6.QtGui import QIcon
    from PyQt6.QtGui import QAction
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 6
except ImportError:
    from PyQt5 import QtGui
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
        QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem,
        QMenu, QMainWindow, QApplication, QCheckBox, QPushButton, QTabWidget,
        QGroupBox, QSpinBox, QDoubleSpinBox, QTextEdit, QFileDialog, QMessageBox
    )
    from PyQt5.QtGui import QIcon
    from PyQt5.QtWidgets import QAction
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 5
from evileye.utils import utils
import sys
from evileye.capture.video_capture_base import CaptureDeviceType
from evileye.capture import VideoCaptureOpencv
from evileye.visualization_modules.configurer import parameters_processing
from evileye.visualization_modules.configurer.configurer_tabs.tracker_widget import TrackerWidget
from .base_tab import BaseTab
from ..validators import (
    ValidatedLineEdit, ValidatedComboBox, ValidatedCheckBox, ValidatedSpinBox, ValidatedDoubleSpinBox,
    Validators, PathValidator, NumericValidator, JSONValidator
)


class TrackerTab(BaseTab):
    def __init__(self, config_params, parent=None):
        # Инициализируем BaseTab с параметрами трекеров
        super().__init__(config_params, parent)
        
        self.default_track_params = self.params[0] if self.params else {}
        self.proj_root = utils.get_project_root()
        self.hor_layouts = []
        self.layout_check_boxes = {}
        self.botsort_check_boxes = []
        self.src_counter = 0
        self.buttons_layouts_number = {}
        self.widgets_counter = 0
        self.layouts_counter = 0

        # Создаем вкладки для трекеров
        self.trackers = []
        self.track_tabs = QTabWidget()
        self.track_tabs.setTabsClosable(True)
        self.track_tabs.tabCloseRequested.connect(self._remove_tab)

        for params in self.params:
            new_tracker = TrackerWidget(params=params)
            self.trackers.append(new_tracker)
            self.track_tabs.addTab(new_tracker, f'Tracker{len(self.trackers) - 1}')

        # Добавляем вкладки трекеров в основной layout
        self.main_layout.addWidget(self.track_tabs)
        
        # Добавляем кнопки управления трекерами
        self._add_tracker_management_buttons()
        
        # Добавляем секцию расширенных параметров BoTSORT
        self._add_botsort_advanced_section()
        
        # Добавляем секцию encoder настроек
        self._add_encoder_section()
        
        # Добавляем секцию multi-camera tracking
        self._add_multi_camera_section()
        
        # Настраиваем валидаторы ПОСЛЕ создания всех атрибутов
        self._setup_validators()
        
        # Подключаем сигналы ПОСЛЕ создания всех атрибутов
        self._connect_signals()
        
        # Добавляем кнопку валидации
        self.add_validate_button()

        if len(self.trackers) > 0:
            self.enable_add_tracker_button()
    
    def _init_ui(self):
        """Переопределяем инициализацию UI без вызова _setup_validators и _connect_signals"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)
    
    def _add_tracker_management_buttons(self):
        """Добавить кнопки управления трекерами"""
        button_layout = QHBoxLayout()
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.add_track_btn = QPushButton('Добавить трекер')
        self.add_track_btn.setMinimumWidth(200)
        self.add_track_btn.setEnabled(False)
        self.add_track_btn.clicked.connect(self._add_tracker)
        
        self.duplicate_track_btn = QPushButton('Дублировать трекер')
        self.duplicate_track_btn.setMinimumWidth(200)
        self.duplicate_track_btn.clicked.connect(self._duplicate_tracker)
        
        self.delete_track_btn = QPushButton('Удалить трекер')
        self.delete_track_btn.setMinimumWidth(200)
        self.delete_track_btn.clicked.connect(self._delete_tracker)
        
        button_layout.addWidget(self.add_track_btn)
        button_layout.addWidget(self.duplicate_track_btn)
        button_layout.addWidget(self.delete_track_btn)
        
        self.main_layout.addLayout(button_layout)
    
    def _add_botsort_advanced_section(self):
        """Добавить секцию расширенных параметров BoTSORT"""
        botsort_layout = self.create_form_layout()
        
        # Заголовок секции
        self.add_section_separator("Расширенные параметры BoTSORT")
        
        # Track high threshold
        self.track_high_thresh = ValidatedDoubleSpinBox()
        self.track_high_thresh.setRange(0.0, 1.0)
        self.track_high_thresh.setSingleStep(0.01)
        self.track_high_thresh.setValue(0.5)
        self.track_high_thresh.setToolTip("Порог для первой ассоциации треков")
        botsort_layout.addRow('Track high threshold:', self.track_high_thresh)
        
        # Track low threshold
        self.track_low_thresh = ValidatedDoubleSpinBox()
        self.track_low_thresh.setRange(0.0, 1.0)
        self.track_low_thresh.setSingleStep(0.01)
        self.track_low_thresh.setValue(0.1)
        self.track_low_thresh.setToolTip("Порог для второй ассоциации треков")
        botsort_layout.addRow('Track low threshold:', self.track_low_thresh)
        
        # New track threshold
        self.new_track_thresh = ValidatedDoubleSpinBox()
        self.new_track_thresh.setRange(0.0, 1.0)
        self.new_track_thresh.setSingleStep(0.01)
        self.new_track_thresh.setValue(0.6)
        self.new_track_thresh.setToolTip("Порог для инициализации нового трека")
        botsort_layout.addRow('New track threshold:', self.new_track_thresh)
        
        # Match threshold
        self.match_thresh = ValidatedDoubleSpinBox()
        self.match_thresh.setRange(0.0, 1.0)
        self.match_thresh.setSingleStep(0.01)
        self.match_thresh.setValue(0.8)
        self.match_thresh.setToolTip("Порог для сопоставления треков")
        botsort_layout.addRow('Match threshold:', self.match_thresh)
        
        # Track buffer
        self.track_buffer = ValidatedSpinBox()
        self.track_buffer.setRange(1, 1000)
        self.track_buffer.setValue(30)
        self.track_buffer.setToolTip("Буфер для расчета времени удаления треков")
        botsort_layout.addRow('Track buffer:', self.track_buffer)
        
        # GMC method
        self.gmc_method = ValidatedComboBox()
        self.gmc_method.addItems(['sparseOptFlow', 'orb', 'ecc', 'none'])
        self.gmc_method.setCurrentText('sparseOptFlow')
        self.gmc_method.setToolTip("Метод глобальной компенсации движения")
        botsort_layout.addRow('GMC method:', self.gmc_method)
        
        # Proximity threshold
        self.proximity_thresh = ValidatedDoubleSpinBox()
        self.proximity_thresh.setRange(0.0, 1.0)
        self.proximity_thresh.setSingleStep(0.01)
        self.proximity_thresh.setValue(0.5)
        self.proximity_thresh.setToolTip("Порог пространственной близости (IoU)")
        botsort_layout.addRow('Proximity threshold:', self.proximity_thresh)
        
        # Appearance threshold
        self.appearance_thresh = ValidatedDoubleSpinBox()
        self.appearance_thresh.setRange(0.0, 1.0)
        self.appearance_thresh.setSingleStep(0.01)
        self.appearance_thresh.setValue(0.25)
        self.appearance_thresh.setToolTip("Порог сходства внешнего вида (ReID)")
        botsort_layout.addRow('Appearance threshold:', self.appearance_thresh)
        
        # With ReID
        self.with_reid = ValidatedCheckBox()
        self.with_reid.setChecked(False)
        self.with_reid.setToolTip("Включить ReID для улучшения трекинга")
        botsort_layout.addRow('With ReID:', self.with_reid)
        
        # Добавляем группу в layout
        self.add_group_box("Расширенные параметры BoTSORT", botsort_layout)
    
    def _add_encoder_section(self):
        """Добавить секцию encoder настроек"""
        encoder_layout = self.create_form_layout()
        
        # Заголовок секции
        self.add_section_separator("Настройки Encoder")
        
        # Включение encoder
        self.enable_encoder = ValidatedCheckBox()
        self.enable_encoder.setChecked(False)
        self.enable_encoder.setToolTip("Включить encoder для извлечения признаков")
        encoder_layout.addRow('Включить encoder:', self.enable_encoder)
        
        # Путь к ONNX модели
        self.encoder_onnx_path = ValidatedLineEdit()
        self.encoder_onnx_path.setPlaceholderText("models/osnet_ain_x1_0_M.onnx")
        self.encoder_onnx_path.setToolTip("Путь к ONNX модели для encoder")
        encoder_layout.addRow('ONNX модель:', self.encoder_onnx_path)
        
        # Кнопка выбора файла
        self.select_onnx_btn = QPushButton('Выбрать файл')
        self.select_onnx_btn.clicked.connect(self._select_onnx_file)
        encoder_layout.addRow('', self.select_onnx_btn)
        
        # Размер изображения для encoder
        self.encoder_input_size = ValidatedSpinBox()
        self.encoder_input_size.setRange(64, 512)
        self.encoder_input_size.setValue(128)
        self.encoder_input_size.setToolTip("Размер входного изображения для encoder")
        encoder_layout.addRow('Размер входа:', self.encoder_input_size)
        
        # Batch size для encoder
        self.encoder_batch_size = ValidatedSpinBox()
        self.encoder_batch_size.setRange(1, 32)
        self.encoder_batch_size.setValue(1)
        self.encoder_batch_size.setToolTip("Размер батча для encoder")
        encoder_layout.addRow('Batch size:', self.encoder_batch_size)
        
        # Device для encoder
        self.encoder_device = ValidatedComboBox()
        self.encoder_device.addItems(['cpu', 'cuda', 'auto'])
        self.encoder_device.setCurrentText('auto')
        self.encoder_device.setToolTip("Устройство для выполнения encoder")
        encoder_layout.addRow('Устройство:', self.encoder_device)
        
        # Добавляем группу в layout
        self.add_group_box("Настройки Encoder", encoder_layout)
        
        # Подключаем сигналы для зависимых полей
        self.enable_encoder.toggled.connect(self._on_encoder_toggled)
        
        # Инициализируем состояние полей
        self._on_encoder_toggled(self.enable_encoder.isChecked())
    
    def _add_multi_camera_section(self):
        """Добавить секцию multi-camera tracking"""
        multi_camera_layout = self.create_form_layout()
        
        # Заголовок секции
        self.add_section_separator("Multi-Camera Tracking")
        
        # Включение multi-camera tracking
        self.enable_multi_camera = ValidatedCheckBox()
        self.enable_multi_camera.setChecked(False)
        self.enable_multi_camera.setToolTip("Включить трекинг между камерами")
        multi_camera_layout.addRow('Включить multi-camera:', self.enable_multi_camera)
        
        # Список source IDs для multi-camera
        self.multi_camera_sources = ValidatedLineEdit()
        self.multi_camera_sources.setPlaceholderText("[0, 1, 2]")
        self.multi_camera_sources.setToolTip("Список ID источников для multi-camera tracking")
        multi_camera_layout.addRow('Source IDs:', self.multi_camera_sources)
        
        # Порог для cross-camera matching
        self.cross_camera_thresh = ValidatedDoubleSpinBox()
        self.cross_camera_thresh.setRange(0.0, 1.0)
        self.cross_camera_thresh.setSingleStep(0.01)
        self.cross_camera_thresh.setValue(0.7)
        self.cross_camera_thresh.setToolTip("Порог для сопоставления между камерами")
        multi_camera_layout.addRow('Cross-camera threshold:', self.cross_camera_thresh)
        
        # Максимальное расстояние для cross-camera
        self.cross_camera_max_distance = ValidatedDoubleSpinBox()
        self.cross_camera_max_distance.setRange(0.0, 1000.0)
        self.cross_camera_max_distance.setSingleStep(1.0)
        self.cross_camera_max_distance.setValue(100.0)
        self.cross_camera_max_distance.setToolTip("Максимальное расстояние для cross-camera matching")
        multi_camera_layout.addRow('Max distance:', self.cross_camera_max_distance)
        
        # Добавляем группу в layout
        self.add_group_box("Настройки Multi-Camera Tracking", multi_camera_layout)
        
        # Подключаем сигналы для зависимых полей
        self.enable_multi_camera.toggled.connect(self._on_multi_camera_toggled)
        
        # Инициализируем состояние полей
        self._on_multi_camera_toggled(self.enable_multi_camera.isChecked())
    
    def _on_encoder_toggled(self, enabled):
        """Обработчик включения/выключения encoder"""
        self.encoder_onnx_path.setEnabled(enabled)
        self.select_onnx_btn.setEnabled(enabled)
        self.encoder_input_size.setEnabled(enabled)
        self.encoder_batch_size.setEnabled(enabled)
        self.encoder_device.setEnabled(enabled)
    
    def _on_multi_camera_toggled(self, enabled):
        """Обработчик включения/выключения multi-camera tracking"""
        self.multi_camera_sources.setEnabled(enabled)
        self.cross_camera_thresh.setEnabled(enabled)
        self.cross_camera_max_distance.setEnabled(enabled)
    
    def _select_onnx_file(self):
        """Выбор ONNX файла"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите ONNX файл", "", "ONNX files (*.onnx)"
        )
        
        if file_path:
            self.encoder_onnx_path.setText(file_path)
    
    def _setup_validators(self):
        """Настройка валидаторов для полей"""
        # Валидаторы для BoTSORT параметров (с проверкой на существование атрибутов)
        if hasattr(self, 'track_high_thresh'):
            self.add_validated_widget("track_high_thresh", self.track_high_thresh,
                                    Validators.CONFIDENCE)
        if hasattr(self, 'track_low_thresh'):
            self.add_validated_widget("track_low_thresh", self.track_low_thresh,
                                    Validators.CONFIDENCE)
        if hasattr(self, 'new_track_thresh'):
            self.add_validated_widget("new_track_thresh", self.new_track_thresh,
                                    Validators.CONFIDENCE)
        if hasattr(self, 'match_thresh'):
            self.add_validated_widget("match_thresh", self.match_thresh,
                                    Validators.CONFIDENCE)
        if hasattr(self, 'track_buffer'):
            self.add_validated_widget("track_buffer", self.track_buffer,
                                    NumericValidator("Track buffer", min_value=1, max_value=1000, integer_only=True))
        if hasattr(self, 'proximity_thresh'):
            self.add_validated_widget("proximity_thresh", self.proximity_thresh,
                                    Validators.CONFIDENCE)
        if hasattr(self, 'appearance_thresh'):
            self.add_validated_widget("appearance_thresh", self.appearance_thresh,
                                    Validators.CONFIDENCE)
        
        # Валидаторы для encoder параметров
        if hasattr(self, 'encoder_onnx_path'):
            self.add_validated_widget("encoder_onnx_path", self.encoder_onnx_path,
                                    PathValidator("ONNX модель", must_exist=True, file_types=['.onnx']))
        if hasattr(self, 'encoder_input_size'):
            self.add_validated_widget("encoder_input_size", self.encoder_input_size,
                                    NumericValidator("Размер входа", min_value=64, max_value=512, integer_only=True))
        if hasattr(self, 'encoder_batch_size'):
            self.add_validated_widget("encoder_batch_size", self.encoder_batch_size,
                                    NumericValidator("Batch size", min_value=1, max_value=32, integer_only=True))
        
        # Валидаторы для multi-camera параметров
        if hasattr(self, 'multi_camera_sources'):
            self.add_validated_widget("multi_camera_sources", self.multi_camera_sources,
                                    Validators.SOURCE_IDS)
        if hasattr(self, 'cross_camera_thresh'):
            self.add_validated_widget("cross_camera_thresh", self.cross_camera_thresh,
                                    Validators.CONFIDENCE)
        if hasattr(self, 'cross_camera_max_distance'):
            self.add_validated_widget("cross_camera_max_distance", self.cross_camera_max_distance,
                                    NumericValidator("Максимальное расстояние", min_value=0.0, max_value=1000.0))
    
    def _connect_signals(self):
        """Подключение сигналов"""
        # Подключаем сигналы изменения конфигурации
        for widget in self.validated_widgets.values():
            if hasattr(widget, 'textChanged'):
                widget.textChanged.connect(self._on_config_changed)
            elif hasattr(widget, 'valueChanged'):
                widget.valueChanged.connect(self._on_config_changed)
            elif hasattr(widget, 'toggled'):
                widget.toggled.connect(self._on_config_changed)

    @pyqtSlot()
    def _duplicate_tracker(self):
        cur_tab = self.track_tabs.currentWidget()
        new_params = copy.deepcopy(cur_tab.get_dict())
        new_tracker = TrackerWidget(new_params)
        self.trackers.append(new_tracker)
        self.track_tabs.addTab(new_tracker, f'Tracker{len(self.trackers) - 1}')

    @pyqtSlot()
    def _delete_tracker(self):
        tab_idx = self.track_tabs.currentIndex()
        self.track_tabs.tabCloseRequested.emit(tab_idx)

    @pyqtSlot(int)
    def _remove_tab(self, idx):
        self.track_tabs.removeTab(idx)
        self.trackers.pop(idx)

    @pyqtSlot()
    def enable_add_tracker_button(self):
        self.add_track_btn.setEnabled(True)
        if hasattr(self, 'label'):
            self.label.hide()
            self.vertical_layout.removeWidget(self.label)
            self.vertical_layout.insertWidget(0, self.track_tabs)

    @pyqtSlot()
    def _add_tracker(self):
        new_params = {key: '' for key in self.default_track_params.keys()}
        new_params['botsort_cfg'] = {key: '' for key in self.default_track_params['botsort_cfg'].keys()}
        # print(new_params)
        new_tracker = TrackerWidget(new_params)
        self.trackers.append(new_tracker)
        self.track_tabs.addTab(new_tracker, f'Tracker{len(self.trackers) - 1}')

    def get_forms(self) -> list[QFormLayout]:
        forms = []
        for tab_idx in range(self.track_tabs.count()):
            tab = self.track_tabs.widget(tab_idx)
            forms.append(tab.get_form())
        # print(forms)
        return forms

    def get_params(self):
        """Получить параметры конфигурации трекеров"""
        tracker_params = []
        for tab_idx in range(self.track_tabs.count()):
            tab = self.track_tabs.widget(tab_idx)
            tracker_params.append(tab.get_dict())
        
        # Добавляем расширенные BoTSORT параметры
        botsort_advanced_params = {
            'track_high_thresh': self.track_high_thresh.get_value(),
            'track_low_thresh': self.track_low_thresh.get_value(),
            'new_track_thresh': self.new_track_thresh.get_value(),
            'match_thresh': self.match_thresh.get_value(),
            'track_buffer': self.track_buffer.get_value(),
            'gmc_method': self.gmc_method.get_value(),
            'proximity_thresh': self.proximity_thresh.get_value(),
            'appearance_thresh': self.appearance_thresh.get_value(),
            'with_reid': self.with_reid.get_value()
        }
        
        # Добавляем encoder параметры
        encoder_params = {
            'enabled': self.enable_encoder.get_value(),
            'onnx_path': self.encoder_onnx_path.get_value(),
            'input_size': self.encoder_input_size.get_value(),
            'batch_size': self.encoder_batch_size.get_value(),
            'device': self.encoder_device.get_value()
        }
        
        # Добавляем multi-camera параметры
        multi_camera_params = {
            'enabled': self.enable_multi_camera.get_value(),
            'sources': self.multi_camera_sources.get_value(),
            'cross_camera_thresh': self.cross_camera_thresh.get_value(),
            'cross_camera_max_distance': self.cross_camera_max_distance.get_value()
        }
        
        return {
            'trackers': tracker_params,
            'botsort_advanced': botsort_advanced_params,
            'encoder': encoder_params,
            'multi_camera': multi_camera_params
        }
    
    def _update_ui_from_params(self):
        """Обновить UI из параметров"""
        # Обновляем BoTSORT параметры
        if 'botsort_advanced' in self.params:
            botsort = self.params['botsort_advanced']
            self.track_high_thresh.setValue(botsort.get('track_high_thresh', 0.5))
            self.track_low_thresh.setValue(botsort.get('track_low_thresh', 0.1))
            self.new_track_thresh.setValue(botsort.get('new_track_thresh', 0.6))
            self.match_thresh.setValue(botsort.get('match_thresh', 0.8))
            self.track_buffer.setValue(botsort.get('track_buffer', 30))
            self.gmc_method.setCurrentText(botsort.get('gmc_method', 'sparseOptFlow'))
            self.proximity_thresh.setValue(botsort.get('proximity_thresh', 0.5))
            self.appearance_thresh.setValue(botsort.get('appearance_thresh', 0.25))
            self.with_reid.setChecked(botsort.get('with_reid', False))
        
        # Обновляем encoder параметры
        if 'encoder' in self.params:
            encoder = self.params['encoder']
            self.enable_encoder.setChecked(encoder.get('enabled', False))
            self.encoder_onnx_path.setText(encoder.get('onnx_path', ''))
            self.encoder_input_size.setValue(encoder.get('input_size', 128))
            self.encoder_batch_size.setValue(encoder.get('batch_size', 1))
            self.encoder_device.setCurrentText(encoder.get('device', 'auto'))
        
        # Обновляем multi-camera параметры
        if 'multi_camera' in self.params:
            multi_cam = self.params['multi_camera']
            self.enable_multi_camera.setChecked(multi_cam.get('enabled', False))
            self.multi_camera_sources.setText(str(multi_cam.get('sources', '')))
            self.cross_camera_thresh.setValue(multi_cam.get('cross_camera_thresh', 0.7))
            self.cross_camera_max_distance.setValue(multi_cam.get('cross_camera_max_distance', 100.0))
