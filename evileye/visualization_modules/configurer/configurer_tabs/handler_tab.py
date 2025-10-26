import copy
import json
try:
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
        QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem,
        QMenu, QMainWindow, QApplication, QCheckBox, QPushButton, QTabWidget,
        QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
        QFileDialog, QSpinBox, QDoubleSpinBox, QTextEdit, QSplitter
    )
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
        QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem,
        QMenu, QMainWindow, QApplication, QCheckBox, QPushButton, QTabWidget,
        QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
        QFileDialog, QSpinBox, QDoubleSpinBox, QTextEdit, QSplitter
    )
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 5
from evileye.utils import utils
from evileye.visualization_modules.configurer import parameters_processing
from evileye.visualization_modules.configurer.configurer_tabs.base_tab import BaseTab
from evileye.visualization_modules.configurer.validators import (
    ValidatedLineEdit, ValidatedSpinBox, ValidatedDoubleSpinBox, 
    ValidatedCheckBox, ValidatedComboBox, Validators
)


class HandlerTab(BaseTab):
    def __init__(self, config_params, database_params):
        super().__init__(config_params)

        self.params = config_params
        self.database_params = database_params
        self.default_src_params = self.database_params['database']
        self.config_result = copy.deepcopy(config_params)

        self.proj_root = utils.get_project_root()
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

        # Основные параметры обработки объектов
        self._setup_objects_handling_section()
        
        # Интеграция с ClassManager
        self._setup_class_manager_section()
        
        # Обработка атрибутов
        self._setup_attributes_handling_section()
        
        # Жизненный цикл объектов
        self._setup_objects_lifecycle_section()

    def _setup_objects_handling_section(self):
        """Настройка секции обработки объектов"""
        layout = self.create_form_layout()
        group_box = self.add_group_box("Основные параметры обработки объектов", layout)
        
        # History length
        self.history_len = ValidatedSpinBox()
        self.history_len.setRange(1, 1000)
        self.history_len.setValue(30)
        self.history_len.setToolTip("Количество кадров для хранения истории объектов")
        self.add_validated_widget("History length", self.history_len, Validators.POSITIVE_INT)
        
        # Lost objects store time
        self.lost_store_time_secs = ValidatedSpinBox()
        self.lost_store_time_secs.setRange(1, 3600)
        self.lost_store_time_secs.setValue(60)
        self.lost_store_time_secs.setToolTip("Время хранения потерянных объектов в секундах")
        self.add_validated_widget("Lost objects store time", self.lost_store_time_secs, Validators.POSITIVE_INT)
        
        # Lost threshold
        self.lost_thresh = ValidatedSpinBox()
        self.lost_thresh.setRange(1, 100)
        self.lost_thresh.setValue(5)
        self.lost_thresh.setToolTip("Порог для определения потерянных объектов")
        self.add_validated_widget("Lost threshold", self.lost_thresh, Validators.POSITIVE_INT)
        
        # Max objects per frame
        self.max_objects_per_frame = ValidatedSpinBox()
        self.max_objects_per_frame.setRange(1, 10000)
        self.max_objects_per_frame.setValue(100)
        self.max_objects_per_frame.setToolTip("Максимальное количество объектов на кадр")
        self.add_validated_widget("Max objects per frame", self.max_objects_per_frame, Validators.POSITIVE_INT)
        
        self.main_layout.addWidget(group_box)

    def _setup_class_manager_section(self):
        """Настройка секции интеграции с ClassManager"""
        layout = QVBoxLayout()
        group_box = self.add_group_box("Управление классами объектов", layout)
        
        # Включить ClassManager
        self.enable_class_manager = ValidatedCheckBox("Использовать ClassManager")
        self.enable_class_manager.setChecked(True)
        self.enable_class_manager.setToolTip("Включить централизованное управление классами объектов")
        self.enable_class_manager.toggled.connect(self._on_class_manager_toggled)
        layout.addWidget(self.enable_class_manager)
        
        # Class mapping table
        self.class_mapping_table = QTableWidget()
        self.class_mapping_table.setColumnCount(3)
        self.class_mapping_table.setHorizontalHeaderLabels(["Class ID", "Class Name", "Description"])
        self.class_mapping_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.class_mapping_table.setMaximumHeight(200)
        self.class_mapping_table.setToolTip("Таблица соответствия ID классов и их названий")
        layout.addWidget(self.class_mapping_table)
        
        # Кнопки управления class mapping
        buttons_layout = QHBoxLayout()
        
        self.add_class_btn = QPushButton("Добавить класс")
        self.add_class_btn.clicked.connect(self._add_class_mapping_row)
        buttons_layout.addWidget(self.add_class_btn)
        
        self.remove_class_btn = QPushButton("Удалить класс")
        self.remove_class_btn.clicked.connect(self._remove_class_mapping_row)
        buttons_layout.addWidget(self.remove_class_btn)
        
        self.import_classes_btn = QPushButton("Импорт из модели")
        self.import_classes_btn.clicked.connect(self._import_classes_from_model)
        buttons_layout.addWidget(self.import_classes_btn)
        
        self.export_classes_btn = QPushButton("Экспорт классов")
        self.export_classes_btn.clicked.connect(self._export_classes)
        buttons_layout.addWidget(self.export_classes_btn)
        
        layout.addLayout(buttons_layout)
        
        # JSON редактор для class mapping
        self.class_mapping_json = ValidatedLineEdit()
        self.class_mapping_json.setPlaceholderText('{"0": "person", "1": "car", ...}')
        self.class_mapping_json.setToolTip("JSON представление class mapping")
        self.class_mapping_json.textChanged.connect(self._on_class_mapping_json_changed)
        layout.addWidget(QLabel("Class Mapping JSON:"))
        layout.addWidget(self.class_mapping_json)
        
        self.main_layout.addWidget(group_box)
        
        # Инициализация состояния
        self._on_class_manager_toggled(True)

    def _setup_attributes_handling_section(self):
        """Настройка секции обработки атрибутов"""
        layout = self.create_form_layout()
        group_box = self.add_group_box("Обработка атрибутов объектов", layout)
        
        # Включить обработку атрибутов
        self.enable_attributes_handling = ValidatedCheckBox("Обрабатывать атрибуты объектов")
        self.enable_attributes_handling.setChecked(False)
        self.enable_attributes_handling.setToolTip("Включить обработку и хранение атрибутов объектов")
        self.enable_attributes_handling.toggled.connect(self._on_attributes_handling_toggled)
        layout.addWidget(self.enable_attributes_handling)
        
        # Максимальное количество атрибутов на объект
        self.max_attributes_per_object = ValidatedSpinBox()
        self.max_attributes_per_object.setRange(1, 100)
        self.max_attributes_per_object.setValue(10)
        self.max_attributes_per_object.setToolTip("Максимальное количество атрибутов на объект")
        self.add_validated_widget("Max attributes per object", self.max_attributes_per_object, Validators.POSITIVE_INT)
        
        # Время кэширования атрибутов
        self.attributes_cache_time = ValidatedSpinBox()
        self.attributes_cache_time.setRange(1, 3600)
        self.attributes_cache_time.setValue(300)
        self.attributes_cache_time.setToolTip("Время кэширования атрибутов в секундах")
        self.add_validated_widget("Attributes cache time", self.attributes_cache_time, Validators.POSITIVE_INT)
        
        # Фильтр атрибутов
        self.attributes_filter = ValidatedLineEdit()
        self.attributes_filter.setPlaceholderText("person,car,truck")
        self.attributes_filter.setToolTip("Список классов объектов для обработки атрибутов (через запятую)")
        self.add_validated_widget("Attributes filter", self.attributes_filter, Validators.SOURCE_IDS)
        
        self.main_layout.addWidget(group_box)
        
        # Инициализация состояния
        self._on_attributes_handling_toggled(False)

    def _setup_objects_lifecycle_section(self):
        """Настройка секции жизненного цикла объектов"""
        layout = self.create_form_layout()
        group_box = self.add_group_box("Жизненный цикл объектов", layout)
        
        # Время жизни объекта
        self.object_lifetime = ValidatedSpinBox()
        self.object_lifetime.setRange(1, 3600)
        self.object_lifetime.setValue(60)
        self.object_lifetime.setToolTip("Время жизни объекта в секундах")
        self.add_validated_widget("Object lifetime", self.object_lifetime, Validators.POSITIVE_INT)
        
        # Минимальное время трекинга
        self.min_tracking_time = ValidatedSpinBox()
        self.min_tracking_time.setRange(1, 100)
        self.min_tracking_time.setValue(5)
        self.min_tracking_time.setToolTip("Минимальное время трекинга объекта в кадрах")
        self.add_validated_widget("Min tracking time", self.min_tracking_time, Validators.POSITIVE_INT)
        
        # Автоматическое удаление старых объектов
        self.auto_cleanup_objects = ValidatedCheckBox("Автоматическая очистка старых объектов")
        self.auto_cleanup_objects.setChecked(True)
        self.auto_cleanup_objects.setToolTip("Автоматически удалять объекты старше указанного времени")
        layout.addWidget(self.auto_cleanup_objects)
        
        # Интервал очистки
        self.cleanup_interval = ValidatedSpinBox()
        self.cleanup_interval.setRange(1, 3600)
        self.cleanup_interval.setValue(300)
        self.cleanup_interval.setToolTip("Интервал автоматической очистки в секундах")
        self.add_validated_widget("Cleanup interval", self.cleanup_interval, Validators.POSITIVE_INT)
        
        self.main_layout.addWidget(group_box)

    def get_forms(self) -> list[QFormLayout]:
        form_layouts = []
        forms = [form for i in range(self.vertical_layout.count()) if isinstance(form := self.vertical_layout.itemAt(i), QFormLayout)]
        form_layouts.extend(forms)
        return form_layouts

    def get_params(self):
        """Получить все параметры Handler Tab"""
        return {
            'objects_handling': self._get_objects_handling_params(),
            'class_manager': self._get_class_manager_params(),
            'attributes_handling': self._get_attributes_handling_params(),
            'objects_lifecycle': self._get_objects_lifecycle_params()
        }

    def _get_objects_handling_params(self):
        """Получить параметры обработки объектов"""
        return {
            'history_len': self.history_len.value(),
            'lost_store_time_secs': self.lost_store_time_secs.value(),
            'lost_thresh': self.lost_thresh.value(),
            'max_objects_per_frame': self.max_objects_per_frame.value()
        }

    def _get_class_manager_params(self):
        """Получить параметры ClassManager"""
        class_mapping = {}
        for row in range(self.class_mapping_table.rowCount()):
            class_id_item = self.class_mapping_table.item(row, 0)
            class_name_item = self.class_mapping_table.item(row, 1)
            if class_id_item and class_name_item:
                class_id = class_id_item.text().strip()
                class_name = class_name_item.text().strip()
                if class_id and class_name:
                    class_mapping[class_id] = class_name
        
        return {
            'enable_class_manager': self.enable_class_manager.isChecked(),
            'class_mapping': class_mapping
        }

    def _get_attributes_handling_params(self):
        """Получить параметры обработки атрибутов"""
        attributes_filter = self.attributes_filter.text().strip()
        filter_list = [item.strip() for item in attributes_filter.split(',') if item.strip()] if attributes_filter else []
        
        return {
            'enable_attributes_handling': self.enable_attributes_handling.isChecked(),
            'max_attributes_per_object': self.max_attributes_per_object.value(),
            'attributes_cache_time': self.attributes_cache_time.value(),
            'attributes_filter': filter_list
        }

    def _get_objects_lifecycle_params(self):
        """Получить параметры жизненного цикла объектов"""
        return {
            'object_lifetime': self.object_lifetime.value(),
            'min_tracking_time': self.min_tracking_time.value(),
            'auto_cleanup_objects': self.auto_cleanup_objects.isChecked(),
            'cleanup_interval': self.cleanup_interval.value()
        }

    def _on_class_manager_toggled(self, checked):
        """Обработка переключения ClassManager"""
        self.class_mapping_table.setEnabled(checked)
        self.add_class_btn.setEnabled(checked)
        self.remove_class_btn.setEnabled(checked)
        self.import_classes_btn.setEnabled(checked)
        self.export_classes_btn.setEnabled(checked)
        self.class_mapping_json.setEnabled(checked)
        
        if checked:
            # Загружаем данные из конфигурации
            self._update_ui_from_params()

    def _on_attributes_handling_toggled(self, checked):
        """Обработка переключения обработки атрибутов"""
        self.max_attributes_per_object.setEnabled(checked)
        self.attributes_cache_time.setEnabled(checked)
        self.attributes_filter.setEnabled(checked)

    def _add_class_mapping_row(self):
        """Добавить строку в таблицу class mapping"""
        row = self.class_mapping_table.rowCount()
        self.class_mapping_table.insertRow(row)
        
        # Class ID
        class_id_item = QTableWidgetItem(str(row))
        self.class_mapping_table.setItem(row, 0, class_id_item)
        
        # Class Name
        class_name_item = QTableWidgetItem("")
        self.class_mapping_table.setItem(row, 1, class_name_item)
        
        # Description
        description_item = QTableWidgetItem("")
        self.class_mapping_table.setItem(row, 2, description_item)
        
        # Обновляем JSON
        self._update_class_mapping_json()

    def _remove_class_mapping_row(self):
        """Удалить выбранную строку из таблицы class mapping"""
        current_row = self.class_mapping_table.currentRow()
        if current_row >= 0:
            self.class_mapping_table.removeRow(current_row)
            self._update_class_mapping_json()

    def _on_class_mapping_json_changed(self):
        """Обработка изменения JSON class mapping"""
        try:
            json_text = self.class_mapping_json.text().strip()
            if json_text:
                class_mapping = json.loads(json_text)
                self._update_class_mapping_table(class_mapping)
        except json.JSONDecodeError:
            pass  # Игнорируем некорректный JSON

    def _update_class_mapping_json(self):
        """Обновить JSON представление class mapping"""
        class_mapping = {}
        for row in range(self.class_mapping_table.rowCount()):
            class_id_item = self.class_mapping_table.item(row, 0)
            class_name_item = self.class_mapping_table.item(row, 1)
            if class_id_item and class_name_item:
                class_id = class_id_item.text().strip()
                class_name = class_name_item.text().strip()
                if class_id and class_name:
                    class_mapping[class_id] = class_name
        
        self.class_mapping_json.setText(json.dumps(class_mapping, indent=2))

    def _update_class_mapping_table(self, class_mapping):
        """Обновить таблицу class mapping из словаря"""
        self.class_mapping_table.setRowCount(len(class_mapping))
        
        for row, (class_id, class_name) in enumerate(class_mapping.items()):
            # Class ID
            class_id_item = QTableWidgetItem(str(class_id))
            self.class_mapping_table.setItem(row, 0, class_id_item)
            
            # Class Name
            class_name_item = QTableWidgetItem(str(class_name))
            self.class_mapping_table.setItem(row, 1, class_name_item)
            
            # Description
            description_item = QTableWidgetItem("")
            self.class_mapping_table.setItem(row, 2, description_item)

    def _import_classes_from_model(self):
        """Импорт классов из файла модели"""
        filename, _ = QFileDialog.getOpenFileName(
            self, 
            "Выберите файл модели", 
            "", 
            "All Files (*);;JSON Files (*.json);;YAML Files (*.yaml);;Text Files (*.txt)"
        )
        
        if filename:
            try:
                # Попытка загрузить классы из файла
                # Это упрощенная реализация - в реальности нужно парсить конкретные форматы моделей
                with open(filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Попытка парсинга как JSON
                try:
                    data = json.loads(content)
                    if 'classes' in data:
                        class_mapping = {str(i): name for i, name in enumerate(data['classes'])}
                        self._update_class_mapping_table(class_mapping)
                        self._update_class_mapping_json()
                        QMessageBox.information(self, "Успех", "Классы успешно импортированы")
                        return
                except json.JSONDecodeError:
                    pass
                
                # Если не JSON, попробуем как простой список
                lines = content.strip().split('\n')
                if lines:
                    class_mapping = {str(i): line.strip() for i, line in enumerate(lines) if line.strip()}
                    self._update_class_mapping_table(class_mapping)
                    self._update_class_mapping_json()
                    QMessageBox.information(self, "Успех", "Классы успешно импортированы")
                
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка импорта классов: {str(e)}")

    def _export_classes(self):
        """Экспорт классов в файл"""
        filename, _ = QFileDialog.getSaveFileName(
            self, 
            "Сохранить классы", 
            "class_mapping.json", 
            "JSON Files (*.json);;All Files (*)"
        )
        
        if filename:
            try:
                class_mapping = {}
                for row in range(self.class_mapping_table.rowCount()):
                    class_id_item = self.class_mapping_table.item(row, 0)
                    class_name_item = self.class_mapping_table.item(row, 1)
                    if class_id_item and class_name_item:
                        class_id = class_id_item.text().strip()
                        class_name = class_name_item.text().strip()
                        if class_id and class_name:
                            class_mapping[class_id] = class_name
                
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(class_mapping, f, indent=2, ensure_ascii=False)
                
                QMessageBox.information(self, "Успех", f"Классы экспортированы в {filename}")
                
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка экспорта классов: {str(e)}")

    def _update_ui_from_params(self):
        """Обновить UI из параметров конфигурации"""
        if not self.params:
            return
        
        # Обновляем основные параметры
        handler_params = self.params.get('objects_handling', {})
        if 'history_len' in handler_params:
            self.history_len.setValue(handler_params['history_len'])
        if 'lost_store_time_secs' in handler_params:
            self.lost_store_time_secs.setValue(handler_params['lost_store_time_secs'])
        if 'lost_thresh' in handler_params:
            self.lost_thresh.setValue(handler_params['lost_thresh'])
        if 'max_objects_per_frame' in handler_params:
            self.max_objects_per_frame.setValue(handler_params['max_objects_per_frame'])
        
        # Обновляем ClassManager
        class_manager_params = self.params.get('class_manager', {})
        if 'enable_class_manager' in class_manager_params:
            self.enable_class_manager.setChecked(class_manager_params['enable_class_manager'])
        if 'class_mapping' in class_manager_params:
            self._update_class_mapping_table(class_manager_params['class_mapping'])
            self._update_class_mapping_json()
        
        # Обновляем обработку атрибутов
        attributes_params = self.params.get('attributes_handling', {})
        if 'enable_attributes_handling' in attributes_params:
            self.enable_attributes_handling.setChecked(attributes_params['enable_attributes_handling'])
        if 'max_attributes_per_object' in attributes_params:
            self.max_attributes_per_object.setValue(attributes_params['max_attributes_per_object'])
        if 'attributes_cache_time' in attributes_params:
            self.attributes_cache_time.setValue(attributes_params['attributes_cache_time'])
        if 'attributes_filter' in attributes_params:
            self.attributes_filter.setText(','.join(attributes_params['attributes_filter']))
        
        # Обновляем жизненный цикл объектов
        lifecycle_params = self.params.get('objects_lifecycle', {})
        if 'object_lifetime' in lifecycle_params:
            self.object_lifetime.setValue(lifecycle_params['object_lifetime'])
        if 'min_tracking_time' in lifecycle_params:
            self.min_tracking_time.setValue(lifecycle_params['min_tracking_time'])
        if 'auto_cleanup_objects' in lifecycle_params:
            self.auto_cleanup_objects.setChecked(lifecycle_params['auto_cleanup_objects'])
        if 'cleanup_interval' in lifecycle_params:
            self.cleanup_interval.setValue(lifecycle_params['cleanup_interval'])
