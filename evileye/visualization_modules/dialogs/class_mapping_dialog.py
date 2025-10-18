import json
import os
from typing import Dict, List, Optional, Tuple
try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
        QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
        QFormLayout, QDialogButtonBox, QMessageBox, QFileDialog,
        QLineEdit, QSpinBox, QComboBox, QCheckBox, QTextEdit,
        QTabWidget, QWidget, QSplitter, QListWidget, QListWidgetItem
    )
    from PyQt6.QtCore import Qt, pyqtSignal, QTimer
    from PyQt6.QtGui import QFont, QColor
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
        QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
        QFormLayout, QDialogButtonBox, QMessageBox, QFileDialog,
        QLineEdit, QSpinBox, QComboBox, QCheckBox, QTextEdit,
        QTabWidget, QWidget, QSplitter, QListWidget, QListWidgetItem
    )
    from PyQt5.QtCore import Qt, pyqtSignal, QTimer
    from PyQt5.QtGui import QFont, QColor
    pyqt_version = 5


class ClassMappingDialog(QDialog):
    """Диалог для редактирования маппинга классов"""
    
    class_mapping_updated = pyqtSignal(dict)  # Сигнал с обновленным маппингом
    
    def __init__(self, parent=None, initial_mapping: Optional[Dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Class Mapping Editor")
        self.setModal(True)
        self.resize(800, 600)
        
        self.class_mapping = initial_mapping or {}
        self._setup_ui()
        self._load_mapping()
        
    def _setup_ui(self):
        """Настройка пользовательского интерфейса"""
        layout = QVBoxLayout(self)
        
        # Верхняя панель с кнопками
        top_layout = QHBoxLayout()
        
        self.add_class_btn = QPushButton("Добавить класс")
        self.add_class_btn.clicked.connect(self._add_class)
        top_layout.addWidget(self.add_class_btn)
        
        self.remove_class_btn = QPushButton("Удалить класс")
        self.remove_class_btn.clicked.connect(self._remove_class)
        top_layout.addWidget(self.remove_class_btn)
        
        self.import_from_model_btn = QPushButton("Импорт из модели")
        self.import_from_model_btn.clicked.connect(self._import_from_model)
        top_layout.addWidget(self.import_from_model_btn)
        
        self.import_from_file_btn = QPushButton("Импорт из файла")
        self.import_from_file_btn.clicked.connect(self._import_from_file)
        top_layout.addWidget(self.import_from_file_btn)
        
        self.export_btn = QPushButton("Экспорт")
        self.export_btn.clicked.connect(self._export_mapping)
        top_layout.addWidget(self.export_btn)
        
        self.clear_btn = QPushButton("Очистить")
        self.clear_btn.clicked.connect(self._clear_mapping)
        top_layout.addWidget(self.clear_btn)
        
        top_layout.addStretch()
        layout.addLayout(top_layout)
        
        # Основная область
        main_layout = QHBoxLayout()
        
        # Левая панель - таблица классов
        left_panel = QVBoxLayout()
        
        # Таблица классов
        self.classes_table = QTableWidget()
        self.classes_table.setColumnCount(3)
        self.classes_table.setHorizontalHeaderLabels(["Class ID", "Class Name", "Description"])
        self.classes_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.classes_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.classes_table.setAlternatingRowColors(True)
        self.classes_table.itemChanged.connect(self._on_table_item_changed)
        self.classes_table.itemSelectionChanged.connect(self._on_selection_changed)
        
        left_panel.addWidget(QLabel("Class Mapping:"))
        left_panel.addWidget(self.classes_table)
        
        # Кнопки управления таблицей
        table_buttons_layout = QHBoxLayout()
        
        self.move_up_btn = QPushButton("↑")
        self.move_up_btn.clicked.connect(self._move_up)
        self.move_up_btn.setEnabled(False)
        table_buttons_layout.addWidget(self.move_up_btn)
        
        self.move_down_btn = QPushButton("↓")
        self.move_down_btn.clicked.connect(self._move_down)
        self.move_down_btn.setEnabled(False)
        table_buttons_layout.addWidget(self.move_down_btn)
        
        table_buttons_layout.addStretch()
        left_panel.addLayout(table_buttons_layout)
        
        main_layout.addLayout(left_panel, 2)
        
        # Правая панель - настройки и предпросмотр
        right_panel = QVBoxLayout()
        
        # Группа настроек
        settings_group = QGroupBox("Настройки")
        settings_layout = QFormLayout(settings_group)
        
        self.auto_id_check = QCheckBox("Автоматическая нумерация ID")
        self.auto_id_check.setChecked(True)
        self.auto_id_check.toggled.connect(self._on_auto_id_toggled)
        settings_layout.addRow("", self.auto_id_check)
        
        self.start_id_spin = QSpinBox()
        self.start_id_spin.setRange(0, 10000)
        self.start_id_spin.setValue(0)
        self.start_id_spin.setEnabled(False)
        settings_layout.addRow("Начальный ID:", self.start_id_spin)
        
        self.validate_mapping_btn = QPushButton("Валидация")
        self.validate_mapping_btn.clicked.connect(self._validate_mapping)
        settings_layout.addRow("", self.validate_mapping_btn)
        
        right_panel.addWidget(settings_group)
        
        # Группа предпросмотра
        preview_group = QGroupBox("Предпросмотр")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(200)
        preview_layout.addWidget(self.preview_text)
        
        self.update_preview_btn = QPushButton("Обновить предпросмотр")
        self.update_preview_btn.clicked.connect(self._update_preview)
        preview_layout.addWidget(self.update_preview_btn)
        
        right_panel.addWidget(preview_group)
        
        # Группа статистики
        stats_group = QGroupBox("Статистика")
        stats_layout = QFormLayout(stats_group)
        
        self.total_classes_label = QLabel("0")
        stats_layout.addRow("Всего классов:", self.total_classes_label)
        
        self.max_id_label = QLabel("0")
        stats_layout.addRow("Максимальный ID:", self.max_id_label)
        
        self.duplicate_ids_label = QLabel("0")
        self.duplicate_ids_label.setStyleSheet("color: red;")
        stats_layout.addRow("Дублирующиеся ID:", self.duplicate_ids_label)
        
        right_panel.addWidget(stats_group)
        
        right_panel.addStretch()
        main_layout.addLayout(right_panel, 1)
        
        layout.addLayout(main_layout)
        
        # Кнопки диалога
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._accept_dialog)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _load_mapping(self):
        """Загрузить маппинг в таблицу"""
        self.classes_table.setRowCount(len(self.class_mapping))
        
        for row, (class_id, class_name) in enumerate(self.class_mapping.items()):
            # Class ID
            id_item = QTableWidgetItem(str(class_id))
            id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable if self.auto_id_check.isChecked() else id_item.flags())
            self.classes_table.setItem(row, 0, id_item)
            
            # Class Name
            name_item = QTableWidgetItem(str(class_name))
            self.classes_table.setItem(row, 1, name_item)
            
            # Description (пустое по умолчанию)
            desc_item = QTableWidgetItem("")
            self.classes_table.setItem(row, 2, desc_item)
        
        self._update_statistics()
        self._update_preview()
    
    def _add_class(self):
        """Добавить новый класс"""
        row = self.classes_table.rowCount()
        self.classes_table.insertRow(row)
        
        # Определяем следующий ID
        if self.auto_id_check.isChecked():
            next_id = self._get_next_id()
        else:
            next_id = self.start_id_spin.value()
        
        # Class ID
        id_item = QTableWidgetItem(str(next_id))
        if self.auto_id_check.isChecked():
            id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.classes_table.setItem(row, 0, id_item)
        
        # Class Name
        name_item = QTableWidgetItem(f"class_{next_id}")
        self.classes_table.setItem(row, 1, name_item)
        
        # Description
        desc_item = QTableWidgetItem("")
        self.classes_table.setItem(row, 2, desc_item)
        
        self._update_statistics()
        self._update_preview()
    
    def _remove_class(self):
        """Удалить выбранный класс"""
        current_row = self.classes_table.currentRow()
        if current_row >= 0:
            class_name = self.classes_table.item(current_row, 1).text()
            
            reply = QMessageBox.question(
                self,
                "Подтверждение",
                f"Удалить класс '{class_name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.classes_table.removeRow(current_row)
                self._update_statistics()
                self._update_preview()
    
    def _move_up(self):
        """Переместить выбранную строку вверх"""
        current_row = self.classes_table.currentRow()
        if current_row > 0:
            self._swap_rows(current_row, current_row - 1)
            self.classes_table.selectRow(current_row - 1)
    
    def _move_down(self):
        """Переместить выбранную строку вниз"""
        current_row = self.classes_table.currentRow()
        if current_row < self.classes_table.rowCount() - 1:
            self._swap_rows(current_row, current_row + 1)
            self.classes_table.selectRow(current_row + 1)
    
    def _swap_rows(self, row1: int, row2: int):
        """Поменять местами две строки"""
        for col in range(self.classes_table.columnCount()):
            item1 = self.classes_table.takeItem(row1, col)
            item2 = self.classes_table.takeItem(row2, col)
            self.classes_table.setItem(row1, col, item2)
            self.classes_table.setItem(row2, col, item1)
    
    def _on_table_item_changed(self, item):
        """Обработка изменения элемента таблицы"""
        if item.column() == 0:  # Class ID
            # Проверяем уникальность ID
            self._validate_ids()
        
        self._update_statistics()
        self._update_preview()
    
    def _on_selection_changed(self):
        """Обработка изменения выбора"""
        current_row = self.classes_table.currentRow()
        has_selection = current_row >= 0
        
        self.remove_class_btn.setEnabled(has_selection)
        self.move_up_btn.setEnabled(has_selection and current_row > 0)
        self.move_down_btn.setEnabled(has_selection and current_row < self.classes_table.rowCount() - 1)
    
    def _on_auto_id_toggled(self, checked):
        """Обработка переключения автоматической нумерации"""
        self.start_id_spin.setEnabled(not checked)
        
        # Обновляем флаги редактирования для всех ID
        for row in range(self.classes_table.rowCount()):
            id_item = self.classes_table.item(row, 0)
            if id_item:
                if checked:
                    id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                else:
                    id_item.setFlags(id_item.flags() | Qt.ItemFlag.ItemIsEditable)
    
    def _get_next_id(self) -> int:
        """Получить следующий доступный ID"""
        used_ids = set()
        for row in range(self.classes_table.rowCount()):
            id_item = self.classes_table.item(row, 0)
            if id_item:
                try:
                    used_ids.add(int(id_item.text()))
                except ValueError:
                    pass
        
        next_id = self.start_id_spin.value()
        while next_id in used_ids:
            next_id += 1
        
        return next_id
    
    def _validate_ids(self):
        """Проверить уникальность ID"""
        ids = []
        for row in range(self.classes_table.rowCount()):
            id_item = self.classes_table.item(row, 0)
            if id_item:
                try:
                    class_id = int(id_item.text())
                    if class_id in ids:
                        # Подсвечиваем дублирующиеся ID
                        id_item.setBackground(QColor(255, 200, 200))
                    else:
                        id_item.setBackground(QColor(255, 255, 255))
                        ids.append(class_id)
                except ValueError:
                    id_item.setBackground(QColor(255, 200, 200))
    
    def _validate_mapping(self):
        """Валидация маппинга"""
        errors = []
        warnings = []
        
        # Проверяем уникальность ID
        ids = []
        for row in range(self.classes_table.rowCount()):
            id_item = self.classes_table.item(row, 0)
            name_item = self.classes_table.item(row, 1)
            
            if not id_item or not name_item:
                continue
            
            try:
                class_id = int(id_item.text())
                class_name = name_item.text().strip()
                
                if not class_name:
                    errors.append(f"Строка {row + 1}: пустое название класса")
                
                if class_id in ids:
                    errors.append(f"Строка {row + 1}: дублирующийся ID {class_id}")
                else:
                    ids.append(class_id)
                
                if class_id < 0:
                    warnings.append(f"Строка {row + 1}: отрицательный ID {class_id}")
                
            except ValueError:
                errors.append(f"Строка {row + 1}: неверный формат ID")
        
        # Проверяем уникальность названий
        names = []
        for row in range(self.classes_table.rowCount()):
            name_item = self.classes_table.item(row, 1)
            if name_item:
                class_name = name_item.text().strip()
                if class_name and class_name in names:
                    warnings.append(f"Строка {row + 1}: дублирующееся название '{class_name}'")
                elif class_name:
                    names.append(class_name)
        
        # Показываем результаты валидации
        if errors or warnings:
            message = "Результаты валидации:\n\n"
            if errors:
                message += "Ошибки:\n" + "\n".join(f"• {error}" for error in errors) + "\n\n"
            if warnings:
                message += "Предупреждения:\n" + "\n".join(f"• {warning}" for warning in warnings)
            
            QMessageBox.warning(self, "Валидация", message)
        else:
            QMessageBox.information(self, "Валидация", "Маппинг классов корректен!")
    
    def _update_statistics(self):
        """Обновить статистику"""
        total_classes = self.classes_table.rowCount()
        self.total_classes_label.setText(str(total_classes))
        
        max_id = 0
        duplicate_count = 0
        ids = []
        
        for row in range(total_classes):
            id_item = self.classes_table.item(row, 0)
            if id_item:
                try:
                    class_id = int(id_item.text())
                    max_id = max(max_id, class_id)
                    if class_id in ids:
                        duplicate_count += 1
                    else:
                        ids.append(class_id)
                except ValueError:
                    pass
        
        self.max_id_label.setText(str(max_id))
        self.duplicate_ids_label.setText(str(duplicate_count))
    
    def _update_preview(self):
        """Обновить предпросмотр"""
        mapping = {}
        for row in range(self.classes_table.rowCount()):
            id_item = self.classes_table.item(row, 0)
            name_item = self.classes_table.item(row, 1)
            
            if id_item and name_item:
                try:
                    class_id = int(id_item.text())
                    class_name = name_item.text().strip()
                    if class_name:
                        mapping[class_id] = class_name
                except ValueError:
                    pass
        
        # Форматируем предпросмотр
        preview_text = "Class Mapping:\n\n"
        for class_id, class_name in sorted(mapping.items()):
            preview_text += f"{class_id}: {class_name}\n"
        
        # JSON предпросмотр
        preview_text += "\nJSON Format:\n"
        preview_text += json.dumps(mapping, indent=2, ensure_ascii=False)
        
        self.preview_text.setPlainText(preview_text)
    
    def _import_from_model(self):
        """Импорт классов из модели"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите файл модели",
            "",
            "Model Files (*.pt *.pth *.onnx);;All Files (*)"
        )
        
        if file_path:
            try:
                # Здесь должна быть логика извлечения классов из модели
                # Пока что показываем заглушку
                QMessageBox.information(
                    self,
                    "Импорт из модели",
                    f"Функция импорта из модели {file_path} будет реализована в будущих версиях.\n"
                    f"Пока что используйте импорт из файла."
                )
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка импорта из модели: {str(e)}")
    
    def _import_from_file(self):
        """Импорт маппинга из файла"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите файл маппинга",
            "",
            "JSON Files (*.json);;Text Files (*.txt);;All Files (*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    if file_path.endswith('.json'):
                        mapping = json.load(f)
                    else:
                        # Пытаемся загрузить как JSON
                        mapping = json.load(f)
                
                # Очищаем текущую таблицу
                self.classes_table.setRowCount(0)
                
                # Добавляем импортированные классы
                for class_id, class_name in mapping.items():
                    self._add_class()
                    row = self.classes_table.rowCount() - 1
                    
                    id_item = QTableWidgetItem(str(class_id))
                    if self.auto_id_check.isChecked():
                        id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.classes_table.setItem(row, 0, id_item)
                    
                    name_item = QTableWidgetItem(str(class_name))
                    self.classes_table.setItem(row, 1, name_item)
                
                self._update_statistics()
                self._update_preview()
                
                QMessageBox.information(self, "Успех", f"Маппинг импортирован из {file_path}")
                
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка импорта: {str(e)}")
    
    def _export_mapping(self):
        """Экспорт маппинга в файл"""
        mapping = self._get_current_mapping()
        if not mapping:
            QMessageBox.information(self, "Информация", "Нет данных для экспорта")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт маппинга",
            "class_mapping.json",
            "JSON Files (*.json);;Text Files (*.txt);;All Files (*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    if file_path.endswith('.json'):
                        json.dump(mapping, f, indent=2, ensure_ascii=False)
                    else:
                        # Экспорт в текстовом формате
                        for class_id, class_name in sorted(mapping.items()):
                            f.write(f"{class_id}: {class_name}\n")
                
                QMessageBox.information(self, "Успех", f"Маппинг экспортирован в {file_path}")
                
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка экспорта: {str(e)}")
    
    def _clear_mapping(self):
        """Очистить маппинг"""
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            "Вы уверены, что хотите очистить весь маппинг?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.classes_table.setRowCount(0)
            self._update_statistics()
            self._update_preview()
    
    def _get_current_mapping(self) -> Dict[int, str]:
        """Получить текущий маппинг из таблицы"""
        mapping = {}
        for row in range(self.classes_table.rowCount()):
            id_item = self.classes_table.item(row, 0)
            name_item = self.classes_table.item(row, 1)
            
            if id_item and name_item:
                try:
                    class_id = int(id_item.text())
                    class_name = name_item.text().strip()
                    if class_name:
                        mapping[class_id] = class_name
                except ValueError:
                    pass
        
        return mapping
    
    def _accept_dialog(self):
        """Принять диалог и отправить сигнал"""
        mapping = self._get_current_mapping()
        self.class_mapping_updated.emit(mapping)
        self.accept()
    
    def get_mapping(self) -> Dict[int, str]:
        """Получить текущий маппинг"""
        return self._get_current_mapping()
    
    def set_mapping(self, mapping: Dict[int, str]):
        """Установить маппинг для редактирования"""
        self.class_mapping = mapping
        self._load_mapping()
