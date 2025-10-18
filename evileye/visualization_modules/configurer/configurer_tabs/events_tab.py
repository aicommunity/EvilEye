import copy
import json
try:
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QHBoxLayout, QLineEdit, QVBoxLayout,
        QSizePolicy, QFormLayout, QPushButton, QSpacerItem,
        QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
        QFileDialog, QSpinBox, QDoubleSpinBox, QTextEdit, QSplitter, QTabWidget,
        QComboBox, QCheckBox, QTimeEdit, QDateEdit, QDateTimeEdit, QScrollArea
    )
    from PyQt6.QtCore import pyqtSlot, Qt, QTime, QDate, QDateTime
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QHBoxLayout, QLineEdit, QVBoxLayout,
        QSizePolicy, QFormLayout, QPushButton, QSpacerItem,
        QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
        QFileDialog, QSpinBox, QDoubleSpinBox, QTextEdit, QSplitter, QTabWidget,
        QComboBox, QCheckBox, QTimeEdit, QDateEdit, QDateTimeEdit, QScrollArea
    )
    from PyQt5.QtCore import pyqtSlot, Qt, QTime, QDate, QDateTime
    pyqt_version = 5
from evileye.utils import utils
from evileye.visualization_modules.configurer import parameters_processing
from evileye.visualization_modules.configurer.configurer_tabs.base_tab import BaseTab
from evileye.visualization_modules.configurer.validators import (
    ValidatedLineEdit, ValidatedSpinBox, ValidatedDoubleSpinBox, 
    ValidatedCheckBox, ValidatedComboBox, Validators
)


class EventsTab(BaseTab):
    def __init__(self, config_params, parent=None):
        super().__init__(config_params, parent)

        self.params = config_params
        self.config_result = copy.deepcopy(config_params)

        self.proj_root = utils.get_project_root()
        self.hor_layouts = []
        self.split_check_boxes = []
        self.botsort_check_boxes = []
        self.coords_edits = []
        self.buttons_layouts_number = {}
        self.widgets_counter = 0
        self.sources_counter = 0
        self.layouts_counter = 0

        # Словарь для сопоставления полей интерфейса с полями json-файла
        self.line_edit_param = {"ZoneEventsDetector": {}, "FieldOfViewEventsDetector": {}, "AttributeEventsDetector": {}}
        
        # Используем main_layout из BaseTab вместо создания нового
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._setup_events_layout()

    def _setup_events_layout(self):
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        # Создаем TabWidget для разных типов событий
        self.events_tab_widget = QTabWidget()
        
        # Zone Events Detector
        self._setup_zone_events_tab()
        
        # Field of View Events Detector
        self._setup_fov_events_tab()
        
        # Attribute Events Detector
        self._setup_attribute_events_tab()
        
        # Events Preview
        self._setup_events_preview_tab()
        
        self.main_layout.addWidget(self.events_tab_widget)

    def _setup_zone_events_tab(self):
        """Настройка вкладки Zone Events Detector"""
        zone_tab = QWidget()
        zone_layout = QVBoxLayout()
        
        # Основные параметры
        layout = self.create_form_layout()
        basic_group = self.add_group_box("Основные параметры Zone Events Detector", layout)
        basic_layout = self.create_form_layout()
        
        self.zone_event_threshold = ValidatedDoubleSpinBox()
        self.zone_event_threshold.setRange(0.0, 1.0)
        self.zone_event_threshold.setSingleStep(0.1)
        self.zone_event_threshold.setValue(0.5)
        self.zone_event_threshold.setToolTip("Порог для детекции событий в зонах")
        self.add_validated_widget("Event threshold", self.zone_event_threshold, Validators.CONFIDENCE)
        
        self.zone_left_threshold = ValidatedDoubleSpinBox()
        self.zone_left_threshold.setRange(0.0, 1.0)
        self.zone_left_threshold.setSingleStep(0.1)
        self.zone_left_threshold.setValue(0.3)
        self.zone_left_threshold.setToolTip("Порог для определения покидания зоны")
        self.add_validated_widget("Zone left threshold", self.zone_left_threshold, Validators.CONFIDENCE)
        
        basic_group.setLayout(basic_layout)
        zone_layout.addWidget(basic_group)
        
        # Управление источниками и зонами
        layout = self.create_form_layout()
        sources_group = self.add_group_box("Источники и зоны", layout)
        sources_layout = QVBoxLayout()
        
        # Кнопки управления
        buttons_layout = QHBoxLayout()
        
        self.add_zone_source_btn = QPushButton("Добавить источник")
        self.add_zone_source_btn.clicked.connect(self._add_zone_source)
        buttons_layout.addWidget(self.add_zone_source_btn)
        
        self.remove_zone_source_btn = QPushButton("Удалить источник")
        self.remove_zone_source_btn.clicked.connect(self._remove_zone_source)
        buttons_layout.addWidget(self.remove_zone_source_btn)
        
        self.visual_zone_editor_btn = QPushButton("Визуальный редактор зон")
        self.visual_zone_editor_btn.clicked.connect(self._open_visual_zone_editor)
        buttons_layout.addWidget(self.visual_zone_editor_btn)
        
        sources_layout.addLayout(buttons_layout)
        
        # Таблица источников и зон
        self.zone_sources_table = QTableWidget()
        self.zone_sources_table.setColumnCount(3)
        self.zone_sources_table.setHorizontalHeaderLabels(["Source ID", "Zones", "Actions"])
        self.zone_sources_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.zone_sources_table.setMaximumHeight(200)
        self.zone_sources_table.setToolTip("Таблица источников и их зон")
        sources_layout.addWidget(self.zone_sources_table)
        
        sources_group.setLayout(sources_layout)
        zone_layout.addWidget(sources_group)
        
        zone_tab.setLayout(zone_layout)
        self.events_tab_widget.addTab(zone_tab, "Zone Events")

    def _setup_fov_events_tab(self):
        """Настройка вкладки Field of View Events Detector"""
        fov_tab = QWidget()
        fov_layout = QVBoxLayout()
        
        # Основные параметры
        layout = self.create_form_layout()
        basic_group = self.add_group_box("Основные параметры FOV Events Detector", layout)
        basic_layout = self.create_form_layout()
        
        self.fov_event_threshold = ValidatedDoubleSpinBox()
        self.fov_event_threshold.setRange(0.0, 1.0)
        self.fov_event_threshold.setSingleStep(0.1)
        self.fov_event_threshold.setValue(0.5)
        self.fov_event_threshold.setToolTip("Порог для детекции событий в поле зрения")
        self.add_validated_widget("Event threshold", self.fov_event_threshold, Validators.CONFIDENCE)
        
        basic_group.setLayout(basic_layout)
        fov_layout.addWidget(basic_group)
        
        # Управление источниками и расписанием
        layout = self.create_form_layout()
        sources_group = self.add_group_box("Источники и расписание", layout)
        sources_layout = QVBoxLayout()
        
        # Кнопки управления
        buttons_layout = QHBoxLayout()
        
        self.add_fov_source_btn = QPushButton("Добавить источник")
        self.add_fov_source_btn.clicked.connect(self._add_fov_source)
        buttons_layout.addWidget(self.add_fov_source_btn)
        
        self.remove_fov_source_btn = QPushButton("Удалить источник")
        self.remove_fov_source_btn.clicked.connect(self._remove_fov_source)
        buttons_layout.addWidget(self.remove_fov_source_btn)
        
        self.time_schedule_editor_btn = QPushButton("Редактор расписания")
        self.time_schedule_editor_btn.clicked.connect(self._open_time_schedule_editor)
        buttons_layout.addWidget(self.time_schedule_editor_btn)
        
        sources_layout.addLayout(buttons_layout)
        
        # Таблица источников и времени
        self.fov_sources_table = QTableWidget()
        self.fov_sources_table.setColumnCount(3)
        self.fov_sources_table.setHorizontalHeaderLabels(["Source ID", "Time Schedule", "Actions"])
        self.fov_sources_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.fov_sources_table.setMaximumHeight(200)
        self.fov_sources_table.setToolTip("Таблица источников и их расписания")
        sources_layout.addWidget(self.fov_sources_table)
        
        sources_group.setLayout(sources_layout)
        fov_layout.addWidget(sources_group)
        
        fov_tab.setLayout(fov_layout)
        self.events_tab_widget.addTab(fov_tab, "FOV Events")

    def _setup_attribute_events_tab(self):
        """Настройка вкладки Attribute Events Detector"""
        attr_tab = QWidget()
        attr_layout = QVBoxLayout()
        
        # Основные параметры
        layout = self.create_form_layout()
        basic_group = self.add_group_box("Основные параметры Attribute Events Detector", layout)
        basic_layout = self.create_form_layout()
        
        self.attr_event_threshold = ValidatedDoubleSpinBox()
        self.attr_event_threshold.setRange(0.0, 1.0)
        self.attr_event_threshold.setSingleStep(0.1)
        self.attr_event_threshold.setValue(0.7)
        self.attr_event_threshold.setToolTip("Порог для детекции событий по атрибутам")
        self.add_validated_widget("Event threshold", self.attr_event_threshold, Validators.CONFIDENCE)
        
        self.attr_confidence_threshold = ValidatedDoubleSpinBox()
        self.attr_confidence_threshold.setRange(0.0, 1.0)
        self.attr_confidence_threshold.setSingleStep(0.1)
        self.attr_confidence_threshold.setValue(0.5)
        self.attr_confidence_threshold.setToolTip("Минимальный confidence для атрибутов")
        self.add_validated_widget("Attribute confidence threshold", self.attr_confidence_threshold, Validators.CONFIDENCE)
        
        basic_group.setLayout(basic_layout)
        attr_layout.addWidget(basic_group)
        
        # Управление источниками и атрибутами
        layout = self.create_form_layout()
        sources_group = self.add_group_box("Источники и атрибуты", layout)
        sources_layout = QVBoxLayout()
        
        # Кнопки управления
        buttons_layout = QHBoxLayout()
        
        self.add_attr_source_btn = QPushButton("Добавить источник")
        self.add_attr_source_btn.clicked.connect(self._add_attr_source)
        buttons_layout.addWidget(self.add_attr_source_btn)
        
        self.remove_attr_source_btn = QPushButton("Удалить источник")
        self.remove_attr_source_btn.clicked.connect(self._remove_attr_source)
        buttons_layout.addWidget(self.remove_attr_source_btn)
        
        self.attr_events_editor_btn = QPushButton("Редактор событий")
        self.attr_events_editor_btn.clicked.connect(self._open_attr_events_editor)
        buttons_layout.addWidget(self.attr_events_editor_btn)
        
        sources_layout.addLayout(buttons_layout)
        
        # Таблица источников и атрибутов
        self.attr_sources_table = QTableWidget()
        self.attr_sources_table.setColumnCount(3)
        self.attr_sources_table.setHorizontalHeaderLabels(["Source ID", "Expected Events", "Actions"])
        self.attr_sources_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.attr_sources_table.setMaximumHeight(200)
        self.attr_sources_table.setToolTip("Таблица источников и ожидаемых событий по атрибутам")
        sources_layout.addWidget(self.attr_sources_table)
        
        sources_group.setLayout(sources_layout)
        attr_layout.addWidget(sources_group)
        
        attr_tab.setLayout(attr_layout)
        self.events_tab_widget.addTab(attr_tab, "Attribute Events")

    def _setup_events_preview_tab(self):
        """Настройка вкладки предпросмотра событий"""
        preview_tab = QWidget()
        preview_layout = QVBoxLayout()
        
        # Информация о настроенных событиях
        layout = self.create_form_layout()
        info_group = self.add_group_box("Информация о событиях", layout)
        info_layout = QVBoxLayout()
        
        self.events_summary = QTextEdit()
        self.events_summary.setReadOnly(True)
        self.events_summary.setMaximumHeight(150)
        self.events_summary.setToolTip("Сводка по всем настроенным событиям")
        info_layout.addWidget(self.events_summary)
        
        # Кнопки управления
        buttons_layout = QHBoxLayout()
        
        self.refresh_preview_btn = QPushButton("Обновить предпросмотр")
        self.refresh_preview_btn.clicked.connect(self._refresh_events_preview)
        buttons_layout.addWidget(self.refresh_preview_btn)
        
        self.validate_events_btn = QPushButton("Валидация событий")
        self.validate_events_btn.clicked.connect(self._validate_events)
        buttons_layout.addWidget(self.validate_events_btn)
        
        self.export_events_btn = QPushButton("Экспорт событий")
        self.export_events_btn.clicked.connect(self._export_events)
        buttons_layout.addWidget(self.export_events_btn)
        
        info_layout.addLayout(buttons_layout)
        info_group.setLayout(info_layout)
        preview_layout.addWidget(info_group)
        
        # Статистика событий
        layout = self.create_form_layout()
        stats_group = self.add_group_box("Статистика событий", layout)
        stats_layout = self.create_form_layout()
        
        self.total_events_label = QLabel("0")
        self.total_events_label.setToolTip("Общее количество настроенных событий")
        stats_layout.addRow("Total events:", self.total_events_label)
        
        self.zone_events_label = QLabel("0")
        self.zone_events_label.setToolTip("Количество событий по зонам")
        stats_layout.addRow("Zone events:", self.zone_events_label)
        
        self.fov_events_label = QLabel("0")
        self.fov_events_label.setToolTip("Количество событий по полю зрения")
        stats_layout.addRow("FOV events:", self.fov_events_label)
        
        self.attr_events_label = QLabel("0")
        self.attr_events_label.setToolTip("Количество событий по атрибутам")
        stats_layout.addRow("Attribute events:", self.attr_events_label)
        
        stats_group.setLayout(stats_layout)
        preview_layout.addWidget(stats_group)
        
        preview_tab.setLayout(preview_layout)
        self.events_tab_widget.addTab(preview_tab, "Events Preview")

    def _add_zone_source(self):
        """Добавить источник для Zone Events"""
        row = self.zone_sources_table.rowCount()
        self.zone_sources_table.insertRow(row)
        
        # Source ID
        source_id_item = QTableWidgetItem("0")
        self.zone_sources_table.setItem(row, 0, source_id_item)
        
        # Zones
        zones_item = QTableWidgetItem("[]")
        self.zone_sources_table.setItem(row, 1, zones_item)
        
        # Actions button
        edit_btn = QPushButton("Редактировать")
        edit_btn.clicked.connect(lambda: self._edit_zone_source(row))
        self.zone_sources_table.setCellWidget(row, 2, edit_btn)

    def _remove_zone_source(self):
        """Удалить источник для Zone Events"""
        current_row = self.zone_sources_table.currentRow()
        if current_row >= 0:
            self.zone_sources_table.removeRow(current_row)

    def _add_fov_source(self):
        """Добавить источник для FOV Events"""
        row = self.fov_sources_table.rowCount()
        self.fov_sources_table.insertRow(row)
        
        # Source ID
        source_id_item = QTableWidgetItem("0")
        self.fov_sources_table.setItem(row, 0, source_id_item)
        
        # Time Schedule
        time_item = QTableWidgetItem("[]")
        self.fov_sources_table.setItem(row, 1, time_item)
        
        # Actions button
        edit_btn = QPushButton("Редактировать")
        edit_btn.clicked.connect(lambda: self._edit_fov_source(row))
        self.fov_sources_table.setCellWidget(row, 2, edit_btn)

    def _remove_fov_source(self):
        """Удалить источник для FOV Events"""
        current_row = self.fov_sources_table.currentRow()
        if current_row >= 0:
            self.fov_sources_table.removeRow(current_row)

    def _add_attr_source(self):
        """Добавить источник для Attribute Events"""
        row = self.attr_sources_table.rowCount()
        self.attr_sources_table.insertRow(row)
        
        # Source ID
        source_id_item = QTableWidgetItem("0")
        self.attr_sources_table.setItem(row, 0, source_id_item)
        
        # Expected Events
        events_item = QTableWidgetItem("{}")
        self.attr_sources_table.setItem(row, 1, events_item)
        
        # Actions button
        edit_btn = QPushButton("Редактировать")
        edit_btn.clicked.connect(lambda: self._edit_attr_source(row))
        self.attr_sources_table.setCellWidget(row, 2, edit_btn)

    def _remove_attr_source(self):
        """Удалить источник для Attribute Events"""
        current_row = self.attr_sources_table.currentRow()
        if current_row >= 0:
            self.attr_sources_table.removeRow(current_row)

    def _edit_zone_source(self, row):
        """Редактировать источник Zone Events"""
        source_id = self.zone_sources_table.item(row, 0).text()
        zones = self.zone_sources_table.item(row, 1).text()
        
        # Здесь можно открыть диалог редактирования
        QMessageBox.information(self, "Редактирование", f"Редактирование источника {source_id} с зонами: {zones}")

    def _edit_fov_source(self, row):
        """Редактировать источник FOV Events"""
        source_id = self.fov_sources_table.item(row, 0).text()
        time_schedule = self.fov_sources_table.item(row, 1).text()
        
        # Здесь можно открыть диалог редактирования
        QMessageBox.information(self, "Редактирование", f"Редактирование источника {source_id} с расписанием: {time_schedule}")

    def _edit_attr_source(self, row):
        """Редактировать источник Attribute Events"""
        source_id = self.attr_sources_table.item(row, 0).text()
        events = self.attr_sources_table.item(row, 1).text()
        
        # Здесь можно открыть диалог редактирования
        QMessageBox.information(self, "Редактирование", f"Редактирование источника {source_id} с событиями: {events}")

    def _open_visual_zone_editor(self):
        """Открыть визуальный редактор зон"""
        QMessageBox.information(self, "Визуальный редактор зон", "Открытие визуального редактора зон...")

    def _open_time_schedule_editor(self):
        """Открыть редактор расписания"""
        QMessageBox.information(self, "Редактор расписания", "Открытие редактора расписания...")

    def _open_attr_events_editor(self):
        """Открыть редактор событий по атрибутам"""
        QMessageBox.information(self, "Редактор событий", "Открытие редактора событий по атрибутам...")

    def _refresh_events_preview(self):
        """Обновить предпросмотр событий"""
        # Подсчитываем события
        zone_events = self.zone_sources_table.rowCount()
        fov_events = self.fov_sources_table.rowCount()
        attr_events = self.attr_sources_table.rowCount()
        total_events = zone_events + fov_events + attr_events
        
        # Обновляем статистику
        self.total_events_label.setText(str(total_events))
        self.zone_events_label.setText(str(zone_events))
        self.fov_events_label.setText(str(fov_events))
        self.attr_events_label.setText(str(attr_events))
        
        # Обновляем сводку
        summary = f"""Сводка по событиям:
        
Zone Events: {zone_events} источников
- Event threshold: {self.zone_event_threshold.value()}
- Zone left threshold: {self.zone_left_threshold.value()}

FOV Events: {fov_events} источников  
- Event threshold: {self.fov_event_threshold.value()}

Attribute Events: {attr_events} источников
- Event threshold: {self.attr_event_threshold.value()}
- Attribute confidence threshold: {self.attr_confidence_threshold.value()}

Общее количество событий: {total_events}
"""
        self.events_summary.setText(summary)

    def _validate_events(self):
        """Валидация событий"""
        errors = []
        
        # Проверяем Zone Events
        for row in range(self.zone_sources_table.rowCount()):
            source_id = self.zone_sources_table.item(row, 0).text()
            zones = self.zone_sources_table.item(row, 1).text()
            
            if not source_id.isdigit():
                errors.append(f"Zone Events: Неверный Source ID '{source_id}' в строке {row+1}")
            
            try:
                json.loads(zones)
            except json.JSONDecodeError:
                errors.append(f"Zone Events: Неверный формат зон '{zones}' в строке {row+1}")
        
        # Проверяем FOV Events
        for row in range(self.fov_sources_table.rowCount()):
            source_id = self.fov_sources_table.item(row, 0).text()
            time_schedule = self.fov_sources_table.item(row, 1).text()
            
            if not source_id.isdigit():
                errors.append(f"FOV Events: Неверный Source ID '{source_id}' в строке {row+1}")
            
            try:
                json.loads(time_schedule)
            except json.JSONDecodeError:
                errors.append(f"FOV Events: Неверный формат расписания '{time_schedule}' в строке {row+1}")
        
        # Проверяем Attribute Events
        for row in range(self.attr_sources_table.rowCount()):
            source_id = self.attr_sources_table.item(row, 0).text()
            events = self.attr_sources_table.item(row, 1).text()
            
            if not source_id.isdigit():
                errors.append(f"Attribute Events: Неверный Source ID '{source_id}' в строке {row+1}")
            
            try:
                json.loads(events)
            except json.JSONDecodeError:
                errors.append(f"Attribute Events: Неверный формат событий '{events}' в строке {row+1}")
        
        if errors:
            error_text = "Найдены ошибки валидации:\n\n" + "\n".join(errors)
            QMessageBox.warning(self, "Ошибки валидации", error_text)
        else:
            QMessageBox.information(self, "Валидация", "Все события прошли валидацию успешно!")

    def _export_events(self):
        """Экспорт событий"""
        filename, _ = QFileDialog.getSaveFileName(
            self, 
            "Экспорт событий", 
            "events_config.json", 
            "JSON Files (*.json);;All Files (*)"
        )
        
        if filename:
            try:
                events_config = self.get_params()
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(events_config, f, indent=2, ensure_ascii=False)
                QMessageBox.information(self, "Успех", f"События экспортированы в {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка экспорта: {str(e)}")

    def get_forms(self) -> list[QFormLayout]:
        form_layouts = []
        for h_layout in self.hor_layouts:
            forms = [form for i in range(h_layout.count()) if isinstance(form := h_layout.itemAt(i), QFormLayout)]
            form_layouts.extend(forms)
        return form_layouts

    def get_params(self):
        """Получить все параметры Events Tab"""
        return {
            'ZoneEventsDetector': self._get_zone_events_params(),
            'FieldOfViewEventsDetector': self._get_fov_events_params(),
            'AttributeEventsDetector': self._get_attribute_events_params()
        }

    def _get_zone_events_params(self):
        """Получить параметры Zone Events Detector"""
        sources = {}
        for row in range(self.zone_sources_table.rowCount()):
            source_id = self.zone_sources_table.item(row, 0).text()
            zones_text = self.zone_sources_table.item(row, 1).text()
            try:
                zones = json.loads(zones_text)
                sources[source_id] = zones
            except json.JSONDecodeError:
                sources[source_id] = []
        
        return {
            'event_threshold': self.zone_event_threshold.value(),
            'zone_left_threshold': self.zone_left_threshold.value(),
            'sources': sources
        }

    def _get_fov_events_params(self):
        """Получить параметры FOV Events Detector"""
        sources = {}
        for row in range(self.fov_sources_table.rowCount()):
            source_id = self.fov_sources_table.item(row, 0).text()
            time_schedule_text = self.fov_sources_table.item(row, 1).text()
            try:
                time_schedule = json.loads(time_schedule_text)
                sources[source_id] = time_schedule
            except json.JSONDecodeError:
                sources[source_id] = []
        
        return {
            'event_threshold': self.fov_event_threshold.value(),
            'sources': sources
        }

    def _get_attribute_events_params(self):
        """Получить параметры Attribute Events Detector"""
        sources = {}
        for row in range(self.attr_sources_table.rowCount()):
            source_id = self.attr_sources_table.item(row, 0).text()
            events_text = self.attr_sources_table.item(row, 1).text()
            try:
                events = json.loads(events_text)
                sources[source_id] = events
            except json.JSONDecodeError:
                sources[source_id] = {}
        
        return {
            'event_threshold': self.attr_event_threshold.value(),
            'attr_confidence_threshold': self.attr_confidence_threshold.value(),
            'sources': sources
        }

    def _update_ui_from_params(self):
        """Обновить UI из параметров конфигурации"""
        if not self.params:
            return
        
        # Обновляем Zone Events
        zone_params = self.params.get('ZoneEventsDetector', {})
        if 'event_threshold' in zone_params:
            self.zone_event_threshold.setValue(zone_params['event_threshold'])
        if 'zone_left_threshold' in zone_params:
            self.zone_left_threshold.setValue(zone_params['zone_left_threshold'])
        if 'sources' in zone_params:
            self._update_zone_sources_table(zone_params['sources'])
        
        # Обновляем FOV Events
        fov_params = self.params.get('FieldOfViewEventsDetector', {})
        if 'event_threshold' in fov_params:
            self.fov_event_threshold.setValue(fov_params['event_threshold'])
        if 'sources' in fov_params:
            self._update_fov_sources_table(fov_params['sources'])
        
        # Обновляем Attribute Events
        attr_params = self.params.get('AttributeEventsDetector', {})
        if 'event_threshold' in attr_params:
            self.attr_event_threshold.setValue(attr_params['event_threshold'])
        if 'attr_confidence_threshold' in attr_params:
            self.attr_confidence_threshold.setValue(attr_params['attr_confidence_threshold'])
        if 'sources' in attr_params:
            self._update_attr_sources_table(attr_params['sources'])

    def _update_zone_sources_table(self, sources):
        """Обновить таблицу источников Zone Events"""
        self.zone_sources_table.setRowCount(len(sources))
        
        for row, (source_id, zones) in enumerate(sources.items()):
            # Source ID
            source_id_item = QTableWidgetItem(str(source_id))
            self.zone_sources_table.setItem(row, 0, source_id_item)
            
            # Zones
            zones_item = QTableWidgetItem(json.dumps(zones))
            self.zone_sources_table.setItem(row, 1, zones_item)
            
            # Actions button
            edit_btn = QPushButton("Редактировать")
            edit_btn.clicked.connect(lambda checked, r=row: self._edit_zone_source(r))
            self.zone_sources_table.setCellWidget(row, 2, edit_btn)

    def _update_fov_sources_table(self, sources):
        """Обновить таблицу источников FOV Events"""
        self.fov_sources_table.setRowCount(len(sources))
        
        for row, (source_id, time_schedule) in enumerate(sources.items()):
            # Source ID
            source_id_item = QTableWidgetItem(str(source_id))
            self.fov_sources_table.setItem(row, 0, source_id_item)
            
            # Time Schedule
            time_item = QTableWidgetItem(json.dumps(time_schedule))
            self.fov_sources_table.setItem(row, 1, time_item)
            
            # Actions button
            edit_btn = QPushButton("Редактировать")
            edit_btn.clicked.connect(lambda checked, r=row: self._edit_fov_source(r))
            self.fov_sources_table.setCellWidget(row, 2, edit_btn)

    def _update_attr_sources_table(self, sources):
        """Обновить таблицу источников Attribute Events"""
        self.attr_sources_table.setRowCount(len(sources))
        
        for row, (source_id, events) in enumerate(sources.items()):
            # Source ID
            source_id_item = QTableWidgetItem(str(source_id))
            self.attr_sources_table.setItem(row, 0, source_id_item)
            
            # Expected Events
            events_item = QTableWidgetItem(json.dumps(events))
            self.attr_sources_table.setItem(row, 1, events_item)
            
            # Actions button
            edit_btn = QPushButton("Редактировать")
            edit_btn.clicked.connect(lambda checked, r=row: self._edit_attr_source(r))
            self.attr_sources_table.setCellWidget(row, 2, edit_btn)
