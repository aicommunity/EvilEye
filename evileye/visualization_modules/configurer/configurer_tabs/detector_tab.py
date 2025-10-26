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
        QGroupBox, QSpinBox, QDoubleSpinBox, QTextEdit, QTableWidget, QTableWidgetItem,
        QHeaderView, QFileDialog, QMessageBox
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
        QGroupBox, QSpinBox, QDoubleSpinBox, QTextEdit, QTableWidget, QTableWidgetItem,
        QHeaderView, QFileDialog, QMessageBox
    )
    from PyQt5.QtGui import QIcon
    from PyQt5.QtWidgets import QAction
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 5
from evileye.visualization_modules.configurer.configurer_tabs.detector_widget import DetectorWidget
from evileye.utils import utils
import sys
from evileye.capture.video_capture_base import CaptureDeviceType
from evileye.capture import VideoCaptureOpencv
from evileye.visualization_modules.configurer import parameters_processing
from .base_tab import BaseTab
from ..validators import (
    ValidatedLineEdit, ValidatedComboBox, ValidatedCheckBox, ValidatedSpinBox, ValidatedDoubleSpinBox,
    Validators, PathValidator, NumericValidator, JSONValidator
)


class DetectorTab(BaseTab):
    tracker_enabled_signal = pyqtSignal()

    def __init__(self, config_params, parent=None):
        # Инициализируем BaseTab с параметрами детекторов
        super().__init__(config_params, parent)
        
        self.default_det_params = self.params[0] if self.params else {}
        self.proj_root = utils.get_project_root()
        self.buttons_layouts_number = {}

        # Создаем вкладки для детекторов
        self.detectors = []
        self.det_tabs = QTabWidget()
        self.det_tabs.setTabsClosable(True)
        self.det_tabs.tabCloseRequested.connect(self._remove_tab)

        for params in self.params:
            new_detector = DetectorWidget(params=params)
            self.detectors.append(new_detector)
            self.det_tabs.addTab(new_detector, f'Detector{len(self.detectors) - 1}')

        # Добавляем вкладки детекторов в основной layout
        self.main_layout.addWidget(self.det_tabs)
        
        # Добавляем кнопки управления детекторами
        self._add_detector_management_buttons()
        
        # Добавляем секцию attributes detection
        self._add_attributes_detection_section()
        
        # Добавляем секцию class mapping
        self._add_class_mapping_section()
        
        # Настраиваем валидаторы ПОСЛЕ создания всех атрибутов
        self._setup_validators()
        
        # Подключаем сигналы ПОСЛЕ создания всех атрибутов
        self._connect_signals()
        
        # Добавляем кнопку валидации
        self.add_validate_button()

        if len(self.detectors) > 0:
            self.tracker_enabled_signal.emit()
    
    def _init_ui(self):
        """Переопределяем инициализацию UI без вызова _setup_validators и _connect_signals"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)
    
    def _add_detector_management_buttons(self):
        """Добавить кнопки управления детекторами"""
        button_layout = QHBoxLayout()
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.add_det_btn = QPushButton('Добавить детектор')
        self.add_det_btn.setMinimumWidth(200)
        self.add_det_btn.clicked.connect(self._add_detector)
        
        self.duplicate_det_btn = QPushButton('Дублировать детектор')
        self.duplicate_det_btn.setMinimumWidth(200)
        self.duplicate_det_btn.clicked.connect(self._duplicate_det)
        
        self.delete_det_btn = QPushButton('Удалить детектор')
        self.delete_det_btn.setMinimumWidth(200)
        self.delete_det_btn.clicked.connect(self._delete_det)
        
        button_layout.addWidget(self.add_det_btn)
        button_layout.addWidget(self.duplicate_det_btn)
        button_layout.addWidget(self.delete_det_btn)
        
        self.main_layout.addLayout(button_layout)
    
    def _add_attributes_detection_section(self):
        """Добавить секцию attributes detection"""
        attributes_layout = self.create_form_layout()
        
        # Заголовок секции
        self.add_section_separator("Детекция атрибутов")
        
        # Включение attributes detection
        self.enable_attributes = ValidatedCheckBox()
        self.enable_attributes.setChecked(False)
        self.enable_attributes.setToolTip("Включить детекцию атрибутов объектов")
        attributes_layout.addRow('Включить детекцию атрибутов:', self.enable_attributes)
        
        # Модель для attributes
        self.attributes_model_path = ValidatedLineEdit()
        self.attributes_model_path.setPlaceholderText("models/yolo11n.pt")
        self.attributes_model_path.setToolTip("Путь к модели для детекции атрибутов")
        attributes_layout.addRow('Модель атрибутов:', self.attributes_model_path)
        
        # Список атрибутов
        self.attributes_list = ValidatedLineEdit()
        self.attributes_list.setPlaceholderText("[\"hard_hat\", \"no_hard_hat\"]")
        self.attributes_list.setToolTip("Список атрибутов для детекции в формате JSON")
        attributes_layout.addRow('Список атрибутов:', self.attributes_list)
        
        # Порог уверенности для атрибутов
        self.attributes_conf_threshold = ValidatedDoubleSpinBox()
        self.attributes_conf_threshold.setRange(0.0, 1.0)
        self.attributes_conf_threshold.setSingleStep(0.01)
        self.attributes_conf_threshold.setValue(0.5)
        self.attributes_conf_threshold.setToolTip("Порог уверенности для детекции атрибутов")
        attributes_layout.addRow('Порог уверенности:', self.attributes_conf_threshold)
        
        # Размер inference для атрибутов
        self.attributes_inference_size = ValidatedSpinBox()
        self.attributes_inference_size.setRange(64, 1024)
        self.attributes_inference_size.setValue(224)
        self.attributes_inference_size.setToolTip("Размер изображения для inference атрибутов")
        attributes_layout.addRow('Размер inference:', self.attributes_inference_size)
        
        # Добавляем группу в layout
        self.add_group_box("Настройки детекции атрибутов", attributes_layout)
        
        # Подключаем сигналы для зависимых полей
        self.enable_attributes.toggled.connect(self._on_attributes_toggled)
        
        # Инициализируем состояние полей
        self._on_attributes_toggled(self.enable_attributes.isChecked())
    
    def _add_class_mapping_section(self):
        """Добавить секцию class mapping"""
        class_mapping_layout = self.create_form_layout()
        
        # Заголовок секции
        self.add_section_separator("Маппинг классов")
        
        # Включение class mapping
        self.enable_class_mapping = ValidatedCheckBox()
        self.enable_class_mapping.setChecked(False)
        self.enable_class_mapping.setToolTip("Включить пользовательский маппинг классов")
        class_mapping_layout.addRow('Включить маппинг классов:', self.enable_class_mapping)
        
        # Таблица class mapping
        self.class_mapping_table = QTableWidget()
        self.class_mapping_table.setColumnCount(2)
        self.class_mapping_table.setHorizontalHeaderLabels(['Имя класса', 'ID класса'])
        self.class_mapping_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.class_mapping_table.setMaximumHeight(200)
        class_mapping_layout.addRow('Маппинг классов:', self.class_mapping_table)
        
        # Кнопки управления таблицей
        table_buttons_layout = QHBoxLayout()
        
        self.add_class_btn = QPushButton('Добавить класс')
        self.add_class_btn.clicked.connect(self._add_class_mapping_row)
        table_buttons_layout.addWidget(self.add_class_btn)
        
        self.remove_class_btn = QPushButton('Удалить класс')
        self.remove_class_btn.clicked.connect(self._remove_class_mapping_row)
        table_buttons_layout.addWidget(self.remove_class_btn)
        
        self.import_classes_btn = QPushButton('Импорт из модели')
        self.import_classes_btn.clicked.connect(self._import_classes_from_model)
        table_buttons_layout.addWidget(self.import_classes_btn)
        
        class_mapping_layout.addRow('', table_buttons_layout)
        
        # JSON редактор для class mapping
        self.class_mapping_json = ValidatedLineEdit()
        self.class_mapping_json.setPlaceholderText('{"person": 0, "car": 2}')
        self.class_mapping_json.setToolTip("JSON маппинг классов (имя -> ID)")
        class_mapping_layout.addRow('JSON маппинг:', self.class_mapping_json)
        
        # Добавляем группу в layout
        self.add_group_box("Настройки маппинга классов", class_mapping_layout)
        
        # Подключаем сигналы
        self.enable_class_mapping.toggled.connect(self._on_class_mapping_toggled)
        self.class_mapping_table.itemChanged.connect(self._on_class_mapping_changed)
        self.class_mapping_json.textChanged.connect(self._on_class_mapping_json_changed)
        
        # Инициализируем состояние полей
        self._on_class_mapping_toggled(self.enable_class_mapping.isChecked())
    
    def _on_attributes_toggled(self, enabled):
        """Обработчик включения/выключения attributes detection"""
        self.attributes_model_path.setEnabled(enabled)
        self.attributes_list.setEnabled(enabled)
        self.attributes_conf_threshold.setEnabled(enabled)
        self.attributes_inference_size.setEnabled(enabled)
    
    def _on_class_mapping_toggled(self, enabled):
        """Обработчик включения/выключения class mapping"""
        self.class_mapping_table.setEnabled(enabled)
        self.class_mapping_json.setEnabled(enabled)
        self.add_class_btn.setEnabled(enabled)
        self.remove_class_btn.setEnabled(enabled)
        self.import_classes_btn.setEnabled(enabled)
    
    def _add_class_mapping_row(self):
        """Добавить строку в таблицу class mapping"""
        row = self.class_mapping_table.rowCount()
        self.class_mapping_table.insertRow(row)
        
        # Добавляем пустые элементы
        self.class_mapping_table.setItem(row, 0, QTableWidgetItem(""))
        self.class_mapping_table.setItem(row, 1, QTableWidgetItem(""))
    
    def _remove_class_mapping_row(self):
        """Удалить выбранную строку из таблицы class mapping"""
        current_row = self.class_mapping_table.currentRow()
        if current_row >= 0:
            self.class_mapping_table.removeRow(current_row)
            self._update_class_mapping_json()
    
    def _on_class_mapping_changed(self):
        """Обработчик изменения таблицы class mapping"""
        self._update_class_mapping_json()
    
    def _on_class_mapping_json_changed(self):
        """Обработчик изменения JSON class mapping"""
        self._update_class_mapping_table()
    
    def _update_class_mapping_json(self):
        """Обновить JSON из таблицы"""
        mapping = {}
        for row in range(self.class_mapping_table.rowCount()):
            name_item = self.class_mapping_table.item(row, 0)
            id_item = self.class_mapping_table.item(row, 1)
            
            if name_item and id_item and name_item.text() and id_item.text():
                try:
                    class_id = int(id_item.text())
                    mapping[name_item.text()] = class_id
                except ValueError:
                    pass
        
        # Обновляем JSON поле (блокируем сигнал чтобы избежать рекурсии)
        self.class_mapping_json.blockSignals(True)
        self.class_mapping_json.setText(json.dumps(mapping, indent=2))
        self.class_mapping_json.blockSignals(False)
    
    def _update_class_mapping_table(self):
        """Обновить таблицу из JSON"""
        try:
            mapping = json.loads(self.class_mapping_json.text())
            
            # Очищаем таблицу
            self.class_mapping_table.setRowCount(0)
            
            # Добавляем строки
            for name, class_id in mapping.items():
                row = self.class_mapping_table.rowCount()
                self.class_mapping_table.insertRow(row)
                self.class_mapping_table.setItem(row, 0, QTableWidgetItem(str(name)))
                self.class_mapping_table.setItem(row, 1, QTableWidgetItem(str(class_id)))
                
        except (json.JSONDecodeError, ValueError):
            pass  # Игнорируем ошибки парсинга
    
    def _import_classes_from_model(self):
        """Импорт классов из модели"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите файл модели", "", "Model files (*.pt *.onnx *.pth)"
        )
        
        if file_path:
            try:
                # Попытка загрузить модель и извлечь классы
                # Это упрощенная версия - в реальности нужно использовать соответствующие библиотеки
                QMessageBox.information(self, "Импорт классов", 
                                      f"Импорт классов из {file_path} будет реализован в следующих версиях")
            except Exception as e:
                QMessageBox.warning(self, "Ошибка импорта", f"Не удалось импортировать классы: {str(e)}")
    
    def _setup_validators(self):
        """Настройка валидаторов для полей"""
        # Валидаторы для attributes detection (с проверкой на существование атрибутов)
        if hasattr(self, 'attributes_model_path'):
            self.add_validated_widget("attributes_model_path", self.attributes_model_path,
                                    Validators.MODEL_PATH)
        if hasattr(self, 'attributes_list'):
            self.add_validated_widget("attributes_list", self.attributes_list,
                                    JSONValidator("Список атрибутов"))
        if hasattr(self, 'attributes_conf_threshold'):
            self.add_validated_widget("attributes_conf_threshold", self.attributes_conf_threshold,
                                    Validators.CONFIDENCE)
        if hasattr(self, 'attributes_inference_size'):
            self.add_validated_widget("attributes_inference_size", self.attributes_inference_size,
                                    NumericValidator("Размер inference", min_value=64, max_value=1024, integer_only=True))
        
        # Валидаторы для class mapping
        if hasattr(self, 'class_mapping_json'):
            self.add_validated_widget("class_mapping_json", self.class_mapping_json,
                                    JSONValidator("JSON маппинг классов"))
    
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
    def _duplicate_det(self):
        cur_tab = self.det_tabs.currentWidget()
        new_params = copy.deepcopy(cur_tab.get_dict())
        new_detector = DetectorWidget(new_params)
        self.detectors.append(new_detector)
        self.det_tabs.addTab(new_detector, f'Detector{len(self.detectors) - 1}')
        if len(self.detectors) == 1:
            self.tracker_enabled_signal.emit()

    @pyqtSlot()
    def _delete_det(self):
        tab_idx = self.det_tabs.currentIndex()
        self.det_tabs.tabCloseRequested.emit(tab_idx)

    @pyqtSlot(int)
    def _remove_tab(self, idx):
        self.det_tabs.removeTab(idx)
        self.detectors.pop(idx)

    @pyqtSlot()
    def _add_detector(self):
        new_params = {key: '' for key in self.default_det_params.keys()}
        new_detector = DetectorWidget(new_params)
        self.detectors.append(new_detector)
        self.det_tabs.addTab(new_detector, f'Detector{len(self.detectors) - 1}')
        if len(self.detectors) == 1:
            self.tracker_enabled_signal.emit()

    def get_forms(self) -> list[QFormLayout]:
        forms = []
        for tab_idx in range(self.det_tabs.count()):
            tab = self.det_tabs.widget(tab_idx)
            forms.append(tab.get_form())
        # print(forms)
        return forms

    def get_params(self):
        """Получить параметры конфигурации детекторов"""
        det_params = []
        for tab_idx in range(self.det_tabs.count()):
            tab = self.det_tabs.widget(tab_idx)
            det_params.append(tab.get_dict())
        
        # Добавляем attributes detection параметры
        attributes_params = {
            'enabled': self.enable_attributes.get_value(),
            'model': self.attributes_model_path.get_value(),
            'attrs': self.attributes_list.get_value(),
            'conf_threshold': self.attributes_conf_threshold.get_value(),
            'inference_size': self.attributes_inference_size.get_value()
        }
        
        # Добавляем class mapping параметры
        class_mapping_params = {
            'enabled': self.enable_class_mapping.get_value(),
            'mapping': self.class_mapping_json.get_value()
        }
        
        return {
            'detectors': det_params,
            'attributes_detection': attributes_params,
            'class_mapping': class_mapping_params
        }
    
    def _update_ui_from_params(self):
        """Обновить UI из параметров"""
        # Обновляем attributes detection параметры
        if 'attributes_detection' in self.params:
            attrs = self.params['attributes_detection']
            self.enable_attributes.setChecked(attrs.get('enabled', False))
            self.attributes_model_path.setText(attrs.get('model', ''))
            self.attributes_list.setText(str(attrs.get('attrs', '')))
            self.attributes_conf_threshold.setValue(attrs.get('conf_threshold', 0.5))
            self.attributes_inference_size.setValue(attrs.get('inference_size', 224))
        
        # Обновляем class mapping параметры
        if 'class_mapping' in self.params:
            mapping = self.params['class_mapping']
            self.enable_class_mapping.setChecked(mapping.get('enabled', False))
            self.class_mapping_json.setText(str(mapping.get('mapping', '')))
