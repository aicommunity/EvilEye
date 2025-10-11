import copy
import json
import os.path
from ..jobs_history_journal import JobsHistory
from ..db_connection_window import DatabaseConnectionWindow
from ....core.logger import get_module_logger
try:
    from PyQt6 import QtGui
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
        QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem, QListView,
        QMenu, QMainWindow, QApplication, QCheckBox, QPushButton, QTabWidget,
        QGroupBox, QSpinBox, QDoubleSpinBox, QTextEdit
    )
    from PyQt6.QtGui import QIcon
    from PyQt6.QtGui import QAction
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
    from PyQt6.QtSql import QSqlQueryModel, QSqlQuery, QSqlDatabase
    pyqt_version = 6
except ImportError:
    from PyQt5 import QtGui
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
        QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem, QListView,
        QMenu, QMainWindow, QApplication, QCheckBox, QPushButton, QTabWidget,
        QGroupBox, QSpinBox, QDoubleSpinBox, QTextEdit
    )
    from PyQt5.QtGui import QIcon
    from PyQt5.QtWidgets import QAction
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
    from PyQt5.QtSql import QSqlQueryModel, QSqlQuery, QSqlDatabase
    pyqt_version = 5
from evileye.capture.video_capture_base import CaptureDeviceType
from evileye.capture import VideoCaptureOpencv
from .. import parameters_processing
from .src_widget import SourceWidget
from .base_tab import BaseTab
from ..validators import (
    ValidatedLineEdit, ValidatedComboBox, ValidatedCheckBox, ValidatedSpinBox,
    Validators, PathValidator, NumericValidator, NetworkValidator
)
import sys
from evileye.utils import utils


class SourcesHistory(QWidget):
    def __init__(self):
        super().__init__()
        self.setMaximumWidth(400)
        sources = QListView()
        self.model = None
        self._setup_model()
        self._setup_list()
        layout = QVBoxLayout()
        layout.addWidget(self.list)
        self.setLayout(layout)

    def _setup_list(self):
        self._setup_model()

        self.list = QListView()
        self.list.setModel(self.model)

    def _setup_model(self):
        self.model = QSqlQueryModel()

        query = QSqlQuery(QSqlDatabase.database('jobs_conn'))
        query.prepare('SELECT full_address FROM camera_information;')
        query.exec()

        self.model.setQuery(query)


class SourcesTab(BaseTab):
    connection_win_signal = pyqtSignal()

    def __init__(self, config_params, creds, parent=None):
        # Инициализируем BaseTab с параметрами источников
        super().__init__(config_params, parent)
        
        self.credentials = creds
        self.default_src_params = self.params[0] if self.params and len(self.params) > 0 else {}
        
        # Создаем вкладки для источников
        self.sources_tabs = QTabWidget()
        self.sources_tabs.setTabsClosable(True)
        self.sources_tabs.tabCloseRequested.connect(self._remove_tab)

        self.sources = []
        if self.params and len(self.params) > 0:
            for params in self.params:
                widget = SourceWidget(params=params, creds=self.credentials, parent=self)
                self.sources.append(widget)
                widget.conn_win_signal.connect(self.connection_win_signal)
                name = str(params.get("source_names", f"Source{len(self.sources)}"))
                self.sources_tabs.addTab(widget, name)

        self.src_history = None
        
        # Добавляем вкладки источников в основной layout
        self.main_layout.addWidget(self.sources_tabs)
        
        # Добавляем кнопки управления источниками
        self._add_source_management_buttons()
        
        # Добавляем секцию preprocessing параметров
        self._add_preprocessing_section()
        
        # Настраиваем валидаторы ПОСЛЕ создания всех атрибутов
        self._setup_validators()
        
        # Подключаем сигналы ПОСЛЕ создания всех атрибутов
        self._connect_signals()
        
        # Добавляем кнопку валидации
        self.add_validate_button()
    
    def _init_ui(self):
        """Переопределяем инициализацию UI без вызова _setup_validators и _connect_signals"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)
    
    def _add_source_management_buttons(self):
        """Добавить кнопки управления источниками"""
        button_layout = QHBoxLayout()
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.add_source_btn = QPushButton('Добавить источник')
        self.add_source_btn.setMinimumWidth(200)
        self.add_source_btn.clicked.connect(self._add_new_source)
        
        self.duplicate_source_btn = QPushButton('Дублировать источник')
        self.duplicate_source_btn.setMinimumWidth(200)
        self.duplicate_source_btn.clicked.connect(self._duplicate_source)
        
        self.delete_source_btn = QPushButton('Удалить источник')
        self.delete_source_btn.setMinimumWidth(200)
        self.delete_source_btn.clicked.connect(self._delete_source)
        
        button_layout.addWidget(self.add_source_btn)
        button_layout.addWidget(self.duplicate_source_btn)
        button_layout.addWidget(self.delete_source_btn)
        
        self.main_layout.addLayout(button_layout)
    
    def _add_preprocessing_section(self):
        """Добавить секцию preprocessing параметров"""
        preprocessing_layout = self.create_form_layout()
        
        # Заголовок секции
        self.add_section_separator("Параметры предобработки")
        
        # Buffering параметры
        self.buffer_size = ValidatedSpinBox()
        self.buffer_size.setRange(1, 1000)
        self.buffer_size.setValue(10)
        self.buffer_size.setToolTip("Размер буфера для кадров (1-1000)")
        preprocessing_layout.addRow('Размер буфера:', self.buffer_size)
        
        # Frame skip параметры
        self.frame_skip = ValidatedSpinBox()
        self.frame_skip.setRange(1, 100)
        self.frame_skip.setValue(1)
        self.frame_skip.setToolTip("Пропускать каждый N-й кадр (1 = без пропуска)")
        preprocessing_layout.addRow('Пропуск кадров:', self.frame_skip)
        
        # Resize параметры
        self.enable_resize = ValidatedCheckBox()
        self.enable_resize.setChecked(False)
        self.enable_resize.setToolTip("Включить изменение размера кадров")
        preprocessing_layout.addRow('Изменить размер:', self.enable_resize)
        
        self.resize_width = ValidatedSpinBox()
        self.resize_width.setRange(64, 4096)
        self.resize_width.setValue(640)
        self.resize_width.setToolTip("Ширина кадра после изменения размера")
        preprocessing_layout.addRow('Ширина:', self.resize_width)
        
        self.resize_height = ValidatedSpinBox()
        self.resize_height.setRange(64, 4096)
        self.resize_height.setValue(480)
        self.resize_height.setToolTip("Высота кадра после изменения размера")
        preprocessing_layout.addRow('Высота:', self.resize_height)
        
        # ROI параметры
        self.enable_roi = ValidatedCheckBox()
        self.enable_roi.setChecked(False)
        self.enable_roi.setToolTip("Включить обрезку по ROI (Region of Interest)")
        preprocessing_layout.addRow('ROI обрезка:', self.enable_roi)
        
        self.roi_coords = ValidatedLineEdit()
        self.roi_coords.setPlaceholderText("[[x1,y1,x2,y2]]")
        self.roi_coords.setToolTip("Координаты ROI в формате [[x1,y1,x2,y2]] (нормализованные 0-1)")
        preprocessing_layout.addRow('ROI координаты:', self.roi_coords)
        
        # GStreamer параметры
        self.add_section_separator("GStreamer настройки")
        
        self.gstreamer_pipeline = ValidatedLineEdit()
        self.gstreamer_pipeline.setPlaceholderText("rtsp://user:pass@ip:port/path")
        self.gstreamer_pipeline.setToolTip("GStreamer pipeline для RTSP потоков")
        preprocessing_layout.addRow('GStreamer pipeline:', self.gstreamer_pipeline)
        
        self.rtsp_username = ValidatedLineEdit()
        self.rtsp_username.setPlaceholderText("admin")
        self.rtsp_username.setToolTip("Имя пользователя для RTSP")
        preprocessing_layout.addRow('RTSP пользователь:', self.rtsp_username)
        
        self.rtsp_password = ValidatedLineEdit()
        self.rtsp_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.rtsp_password.setPlaceholderText("password")
        self.rtsp_password.setToolTip("Пароль для RTSP")
        preprocessing_layout.addRow('RTSP пароль:', self.rtsp_password)
        
        # Добавляем группу в layout
        self.add_group_box("Настройки предобработки", preprocessing_layout)
        
        # Подключаем сигналы для зависимых полей
        self.enable_resize.toggled.connect(self._on_resize_toggled)
        self.enable_roi.toggled.connect(self._on_roi_toggled)
        
        # Инициализируем состояние полей
        self._on_resize_toggled(self.enable_resize.isChecked())
        self._on_roi_toggled(self.enable_roi.isChecked())
    
    def _on_resize_toggled(self, enabled):
        """Обработчик включения/выключения изменения размера"""
        self.resize_width.setEnabled(enabled)
        self.resize_height.setEnabled(enabled)
    
    def _on_roi_toggled(self, enabled):
        """Обработчик включения/выключения ROI"""
        self.roi_coords.setEnabled(enabled)
    
    def _setup_validators(self):
        """Настройка валидаторов для полей"""
        # Валидаторы для preprocessing параметров (с проверкой на существование атрибутов)
        if hasattr(self, 'buffer_size'):
            self.add_validated_widget("buffer_size", self.buffer_size, 
                                    NumericValidator("Размер буфера", min_value=1, max_value=1000, integer_only=True))
        if hasattr(self, 'frame_skip'):
            self.add_validated_widget("frame_skip", self.frame_skip,
                                    NumericValidator("Пропуск кадров", min_value=1, max_value=100, integer_only=True))
        if hasattr(self, 'resize_width'):
            self.add_validated_widget("resize_width", self.resize_width,
                                    NumericValidator("Ширина", min_value=64, max_value=4096, integer_only=True))
        if hasattr(self, 'resize_height'):
            self.add_validated_widget("resize_height", self.resize_height,
                                    NumericValidator("Высота", min_value=64, max_value=4096, integer_only=True))
        if hasattr(self, 'roi_coords'):
            self.add_validated_widget("roi_coords", self.roi_coords,
                                    Validators.SOURCE_IDS)  # Используем валидатор списков для координат
        if hasattr(self, 'gstreamer_pipeline'):
            self.add_validated_widget("gstreamer_pipeline", self.gstreamer_pipeline,
                                    NetworkValidator("GStreamer pipeline", check_connectivity=False))
    
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
    def _duplicate_source(self):
        cur_tab = self.sources_tabs.currentWidget()
        new_params = copy.deepcopy(cur_tab.get_dict())
        new_source = SourceWidget(new_params, self.credentials)
        new_source.conn_win_signal.connect(self.connection_win_signal)
        self.sources.append(new_source)
        self.sources_tabs.addTab(new_source, f'Source{len(self.sources)}')

    @pyqtSlot()
    def _delete_source(self):
        tab_idx = self.sources_tabs.currentIndex()
        self.sources_tabs.tabCloseRequested.emit(tab_idx)

    @pyqtSlot(int)
    def _remove_tab(self, idx):
        self.sources_tabs.removeTab(idx)
        self.sources.pop(idx)

    def open_src_list(self):
        active_tab = self.sources_tabs.currentWidget()
        if not self.src_history:
            self.src_history = SourcesHistory()
        for tab_idx in range(self.sources_tabs.count()):
            tab = self.sources_tabs.widget(tab_idx)
            tab.history_btn.setEnabled(True)
        active_tab.setEnabled(True)
        active_tab.show_src_history(self.src_history)

    @pyqtSlot()
    def _add_new_source(self):
        new_params = {key: '' for key in self.default_src_params.keys()}
        new_source = SourceWidget(new_params, self.credentials)
        new_source.conn_win_signal.connect(self.connection_win_signal)
        self.sources.append(new_source)
        self.sources_tabs.addTab(new_source, f'Source{len(self.sources)}')

    def get_params(self):
        """Получить параметры конфигурации источников"""
        sources_params = []
        for tab_idx in range(self.sources_tabs.count()):
            tab = self.sources_tabs.widget(tab_idx)
            sources_params.append(tab.get_dict())
        
        # Добавляем preprocessing параметры (с проверкой на существование атрибутов)
        preprocessing_params = {}
        if hasattr(self, 'buffer_size'):
            preprocessing_params['buffer_size'] = self.buffer_size.get_value()
        if hasattr(self, 'frame_skip'):
            preprocessing_params['frame_skip'] = self.frame_skip.get_value()
        if hasattr(self, 'enable_resize'):
            preprocessing_params['enable_resize'] = self.enable_resize.get_value()
        if hasattr(self, 'resize_width'):
            preprocessing_params['resize_width'] = self.resize_width.get_value()
        if hasattr(self, 'resize_height'):
            preprocessing_params['resize_height'] = self.resize_height.get_value()
        if hasattr(self, 'enable_roi'):
            preprocessing_params['enable_roi'] = self.enable_roi.get_value()
        if hasattr(self, 'roi_coords'):
            preprocessing_params['roi_coords'] = self.roi_coords.get_value()
        if hasattr(self, 'gstreamer_pipeline'):
            preprocessing_params['gstreamer_pipeline'] = self.gstreamer_pipeline.get_value()
        if hasattr(self, 'rtsp_username'):
            preprocessing_params['rtsp_username'] = self.rtsp_username.get_value()
        if hasattr(self, 'rtsp_password'):
            preprocessing_params['rtsp_password'] = self.rtsp_password.get_value()
        
        return {
            'sources': sources_params,
            'preprocessing': preprocessing_params
        }
    
    def _update_ui_from_params(self):
        """Обновить UI из параметров"""
        # Обновляем preprocessing параметры (с проверкой на существование атрибутов)
        if 'preprocessing' in self.params:
            preproc = self.params['preprocessing']
            if hasattr(self, 'buffer_size'):
                self.buffer_size.setValue(preproc.get('buffer_size', 10))
            if hasattr(self, 'frame_skip'):
                self.frame_skip.setValue(preproc.get('frame_skip', 1))
            if hasattr(self, 'enable_resize'):
                self.enable_resize.setChecked(preproc.get('enable_resize', False))
            if hasattr(self, 'resize_width'):
                self.resize_width.setValue(preproc.get('resize_width', 640))
            if hasattr(self, 'resize_height'):
                self.resize_height.setValue(preproc.get('resize_height', 480))
            if hasattr(self, 'enable_roi'):
                self.enable_roi.setChecked(preproc.get('enable_roi', False))
            if hasattr(self, 'roi_coords'):
                self.roi_coords.setText(str(preproc.get('roi_coords', '')))
            if hasattr(self, 'gstreamer_pipeline'):
                self.gstreamer_pipeline.setText(preproc.get('gstreamer_pipeline', ''))
            if hasattr(self, 'rtsp_username'):
                self.rtsp_username.setText(preproc.get('rtsp_username', ''))
            if hasattr(self, 'rtsp_password'):
                self.rtsp_password.setText(preproc.get('rtsp_password', ''))

    def closeEvent(self, event) -> None:
        for source in self.sources:
            source.close()
        event.accept()

    def get_forms(self) -> list[QFormLayout]:
        forms = []
        for tab_idx in range(self.sources_tabs.count()):
            tab = self.sources_tabs.widget(tab_idx)
            forms.append(tab.get_form())
        # print(forms)
        return forms
