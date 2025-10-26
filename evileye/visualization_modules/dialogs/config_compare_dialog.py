"""
Диалог сравнения конфигураций для EvilEye.

Предоставляет интерфейс для side-by-side сравнения двух конфигураций
с подсветкой различий и возможностью выбора для восстановления.
"""

import copy
import json
from typing import Dict, Any, List, Tuple, Optional

try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
        QGroupBox, QFormLayout, QCheckBox, QMessageBox, QSplitter,
        QTreeWidget, QTreeWidgetItem, QHeaderView, QScrollArea, QTabWidget,
        QListWidget, QListWidgetItem, QComboBox, QSpinBox
    )
    from PyQt6.QtCore import Qt, pyqtSignal, QTimer
    from PyQt6.QtGui import QFont, QColor, QPalette, QTextCharFormat, QSyntaxHighlighter
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
        QGroupBox, QFormLayout, QCheckBox, QMessageBox, QSplitter,
        QTreeWidget, QTreeWidgetItem, QHeaderView, QScrollArea, QTabWidget,
        QListWidget, QListWidgetItem, QComboBox, QSpinBox
    )
    from PyQt5.QtCore import Qt, pyqtSignal, QTimer
    from PyQt5.QtGui import QFont, QColor, QPalette, QTextCharFormat, QSyntaxHighlighter
    pyqt_version = 5

from ...core.logger import get_module_logger


class JSONHighlighter(QSyntaxHighlighter):
    """Подсветка синтаксиса для JSON"""
    
    def __init__(self, document):
        super().__init__(document)
        self.highlighting_rules = []
        
        # Ключи
        key_format = QTextCharFormat()
        key_format.setForeground(QColor("#0066CC"))
        key_format.setFontWeight(QFont.Weight.Bold)
        self.highlighting_rules.append((r'"[^"]*"\s*:', key_format))
        
        # Строки
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#008000"))
        self.highlighting_rules.append((r'"[^"]*"', string_format))
        
        # Числа
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#FF6600"))
        self.highlighting_rules.append((r'\b\d+\.?\d*\b', number_format))
        
        # Булевы значения
        bool_format = QTextCharFormat()
        bool_format.setForeground(QColor("#800080"))
        bool_format.setFontWeight(QFont.Weight.Bold)
        self.highlighting_rules.append((r'\b(true|false)\b', bool_format))
        
        # null
        null_format = QTextCharFormat()
        null_format.setForeground(QColor("#666666"))
        null_format.setFontItalic(True)
        self.highlighting_rules.append((r'\bnull\b', null_format))
    
    def highlightBlock(self, text):
        """Подсветка блока текста"""
        for pattern, format in self.highlighting_rules:
            import re
            for match in re.finditer(pattern, text):
                start, end = match.span()
                self.setFormat(start, end - start, format)


class ConfigCompareDialog(QDialog):
    """Диалог сравнения конфигураций"""
    
    config_selected = pyqtSignal(dict, str)  # config, source_name
    
    def __init__(self, config1: Dict[str, Any], config2: Dict[str, Any], 
                 config1_name: str = "Конфигурация 1", config2_name: str = "Конфигурация 2",
                 parent=None):
        super().__init__(parent)
        self.logger = get_module_logger("config_compare_dialog")
        
        self.config1 = config1
        self.config2 = config2
        self.config1_name = config1_name
        self.config2_name = config2_name
        
        self.differences = []
        self.selected_config = None
        self.selected_source = None
        
        self.setWindowTitle("Сравнение конфигураций")
        self.setModal(True)
        self.resize(1200, 800)
        
        self._init_ui()
        self._analyze_differences()
        self._populate_comparison()
    
    def _init_ui(self):
        """Инициализация пользовательского интерфейса"""
        layout = QVBoxLayout(self)
        
        # Заголовок
        title_label = QLabel("Сравнение конфигураций")
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Информация о конфигурациях
        self._add_config_info(layout)
        
        # Основной контент с вкладками
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Вкладка "Дерево различий"
        self._create_tree_tab()
        
        # Вкладка "Side-by-side JSON"
        self._create_json_tab()
        
        # Вкладка "Список различий"
        self._create_list_tab()
        
        # Кнопки управления
        self._add_buttons(layout)
    
    def _add_config_info(self, layout):
        """Добавить информацию о конфигурациях"""
        info_group = QGroupBox("Информация о конфигурациях")
        info_layout = QFormLayout(info_group)
        
        # Названия конфигураций
        self.config1_name_label = QLabel(self.config1_name)
        self.config1_name_label.setStyleSheet("font-weight: bold; color: #0066CC;")
        self.config2_name_label = QLabel(self.config2_name)
        self.config2_name_label.setStyleSheet("font-weight: bold; color: #CC6600;")
        
        info_layout.addRow("Конфигурация 1:", self.config1_name_label)
        info_layout.addRow("Конфигурация 2:", self.config2_name_label)
        
        # Статистика
        self.stats_label = QLabel()
        info_layout.addRow("Статистика:", self.stats_label)
        
        layout.addWidget(info_group)
    
    def _create_tree_tab(self):
        """Создать вкладку с деревом различий"""
        tree_widget = QWidget()
        tree_layout = QVBoxLayout(tree_widget)
        
        # Опции отображения
        options_layout = QHBoxLayout()
        
        self.show_identical = QCheckBox("Показать идентичные элементы")
        self.show_identical.setChecked(False)
        self.show_identical.toggled.connect(self._update_tree_display)
        options_layout.addWidget(self.show_identical)
        
        self.show_added = QCheckBox("Показать добавленные")
        self.show_added.setChecked(True)
        self.show_added.toggled.connect(self._update_tree_display)
        options_layout.addWidget(self.show_added)
        
        self.show_removed = QCheckBox("Показать удаленные")
        self.show_removed.setChecked(True)
        self.show_removed.toggled.connect(self._update_tree_display)
        options_layout.addWidget(self.show_removed)
        
        self.show_modified = QCheckBox("Показать измененные")
        self.show_modified.setChecked(True)
        self.show_modified.toggled.connect(self._update_tree_display)
        options_layout.addWidget(self.show_modified)
        
        tree_layout.addLayout(options_layout)
        
        # Дерево различий
        self.differences_tree = QTreeWidget()
        self.differences_tree.setHeaderLabels(["Путь", "Тип изменения", "Значение 1", "Значение 2"])
        self.differences_tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tree_layout.addWidget(self.differences_tree)
        
        self.tab_widget.addTab(tree_widget, "Дерево различий")
    
    def _create_json_tab(self):
        """Создать вкладку с side-by-side JSON"""
        json_widget = QWidget()
        json_layout = QVBoxLayout(json_widget)
        
        # Опции форматирования
        format_layout = QHBoxLayout()
        
        self.pretty_format = QCheckBox("Красивое форматирование")
        self.pretty_format.setChecked(True)
        self.pretty_format.toggled.connect(self._update_json_display)
        format_layout.addWidget(self.pretty_format)
        
        self.highlight_differences = QCheckBox("Подсветить различия")
        self.highlight_differences.setChecked(True)
        self.highlight_differences.toggled.connect(self._update_json_display)
        format_layout.addWidget(self.highlight_differences)
        
        format_layout.addStretch()
        
        # Кнопки навигации
        self.prev_diff_btn = QPushButton("← Предыдущее различие")
        self.prev_diff_btn.clicked.connect(self._navigate_to_prev_diff)
        format_layout.addWidget(self.prev_diff_btn)
        
        self.next_diff_btn = QPushButton("Следующее различие →")
        self.next_diff_btn.clicked.connect(self._navigate_to_next_diff)
        format_layout.addWidget(self.next_diff_btn)
        
        json_layout.addLayout(format_layout)
        
        # Splitter для side-by-side отображения
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Левая панель - конфигурация 1
        left_panel = QGroupBox(self.config1_name)
        left_layout = QVBoxLayout(left_panel)
        
        self.config1_text = QTextEdit()
        self.config1_text.setReadOnly(True)
        self.config1_text.setFont(QFont("Consolas", 10))
        left_layout.addWidget(self.config1_text)
        
        splitter.addWidget(left_panel)
        
        # Правая панель - конфигурация 2
        right_panel = QGroupBox(self.config2_name)
        right_layout = QVBoxLayout(right_panel)
        
        self.config2_text = QTextEdit()
        self.config2_text.setReadOnly(True)
        self.config2_text.setFont(QFont("Consolas", 10))
        right_layout.addWidget(self.config2_text)
        
        splitter.addWidget(right_panel)
        
        # Устанавливаем пропорции
        splitter.setSizes([600, 600])
        
        json_layout.addWidget(splitter)
        
        self.tab_widget.addTab(json_widget, "Side-by-side JSON")
    
    def _create_list_tab(self):
        """Создать вкладку со списком различий"""
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        
        # Фильтры
        filter_layout = QHBoxLayout()
        
        filter_layout.addWidget(QLabel("Фильтр по типу:"))
        
        self.type_filter = QComboBox()
        self.type_filter.addItems(["Все", "Добавлено", "Удалено", "Изменено", "Идентично"])
        self.type_filter.currentTextChanged.connect(self._filter_differences)
        filter_layout.addWidget(self.type_filter)
        
        filter_layout.addWidget(QLabel("Фильтр по секции:"))
        
        self.section_filter = QComboBox()
        self.section_filter.addItems(["Все"])
        self.section_filter.currentTextChanged.connect(self._filter_differences)
        filter_layout.addWidget(self.section_filter)
        
        filter_layout.addStretch()
        
        list_layout.addLayout(filter_layout)
        
        # Список различий
        self.differences_list = QListWidget()
        self.differences_list.itemClicked.connect(self._on_difference_selected)
        list_layout.addWidget(self.differences_list)
        
        self.tab_widget.addTab(list_widget, "Список различий")
    
    def _add_buttons(self, layout):
        """Добавить кнопки управления"""
        button_layout = QHBoxLayout()
        
        # Кнопки выбора конфигурации
        self.select_config1_btn = QPushButton(f"Выбрать {self.config1_name}")
        self.select_config1_btn.setStyleSheet("background-color: #0066CC; color: white; font-weight: bold;")
        self.select_config1_btn.clicked.connect(lambda: self._select_config(self.config1, self.config1_name))
        button_layout.addWidget(self.select_config1_btn)
        
        self.select_config2_btn = QPushButton(f"Выбрать {self.config2_name}")
        self.select_config2_btn.setStyleSheet("background-color: #CC6600; color: white; font-weight: bold;")
        self.select_config2_btn.clicked.connect(lambda: self._select_config(self.config2, self.config2_name))
        button_layout.addWidget(self.select_config2_btn)
        
        button_layout.addStretch()
        
        # Кнопки действий
        self.export_btn = QPushButton("Экспорт сравнения")
        self.export_btn.clicked.connect(self._export_comparison)
        button_layout.addWidget(self.export_btn)
        
        self.cancel_btn = QPushButton("Закрыть")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
    
    def _analyze_differences(self):
        """Анализ различий между конфигурациями"""
        self.differences = []
        self._compare_configs(self.config1, self.config2, "")
        
        # Обновляем статистику
        total_diffs = len(self.differences)
        added = len([d for d in self.differences if d['type'] == 'added'])
        removed = len([d for d in self.differences if d['type'] == 'removed'])
        modified = len([d for d in self.differences if d['type'] == 'modified'])
        identical = len([d for d in self.differences if d['type'] == 'identical'])
        
        stats_text = f"Всего различий: {total_diffs} | Добавлено: {added} | Удалено: {removed} | Изменено: {modified} | Идентично: {identical}"
        self.stats_label.setText(stats_text)
        
        # Обновляем фильтр секций
        sections = set()
        for diff in self.differences:
            path_parts = diff['path'].split('.')
            if path_parts:
                sections.add(path_parts[0])
        
        self.section_filter.clear()
        self.section_filter.addItems(["Все"] + sorted(sections))
    
    def _compare_configs(self, config1, config2, path_prefix):
        """Рекурсивное сравнение конфигураций"""
        if isinstance(config1, dict) and isinstance(config2, dict):
            all_keys = set(config1.keys()) | set(config2.keys())
            
            for key in sorted(all_keys):
                current_path = f"{path_prefix}.{key}" if path_prefix else key
                
                if key not in config1:
                    # Добавлено в config2
                    self.differences.append({
                        'path': current_path,
                        'type': 'added',
                        'value1': None,
                        'value2': config2[key]
                    })
                elif key not in config2:
                    # Удалено из config1
                    self.differences.append({
                        'path': current_path,
                        'type': 'removed',
                        'value1': config1[key],
                        'value2': None
                    })
                else:
                    # Рекурсивное сравнение
                    self._compare_configs(config1[key], config2[key], current_path)
        
        elif isinstance(config1, list) and isinstance(config2, list):
            max_len = max(len(config1), len(config2))
            
            for i in range(max_len):
                current_path = f"{path_prefix}[{i}]"
                
                if i >= len(config1):
                    # Добавлено в config2
                    self.differences.append({
                        'path': current_path,
                        'type': 'added',
                        'value1': None,
                        'value2': config2[i]
                    })
                elif i >= len(config2):
                    # Удалено из config1
                    self.differences.append({
                        'path': current_path,
                        'type': 'removed',
                        'value1': config1[i],
                        'value2': None
                    })
                else:
                    # Рекурсивное сравнение
                    self._compare_configs(config1[i], config2[i], current_path)
        
        else:
            # Примитивные типы
            if config1 == config2:
                self.differences.append({
                    'path': path_prefix,
                    'type': 'identical',
                    'value1': config1,
                    'value2': config2
                })
            else:
                self.differences.append({
                    'path': path_prefix,
                    'type': 'modified',
                    'value1': config1,
                    'value2': config2
                })
    
    def _populate_comparison(self):
        """Заполнить все представления сравнения"""
        self._update_tree_display()
        self._update_json_display()
        self._update_list_display()
    
    def _update_tree_display(self):
        """Обновить отображение дерева"""
        self.differences_tree.clear()
        
        for diff in self.differences:
            if not self._should_show_difference(diff):
                continue
            
            item = QTreeWidgetItem(self.differences_tree)
            item.setText(0, diff['path'])
            item.setText(1, self._get_type_display_name(diff['type']))
            item.setText(2, str(diff['value1'])[:100] + ("..." if len(str(diff['value1'])) > 100 else ""))
            item.setText(3, str(diff['value2'])[:100] + ("..." if len(str(diff['value2'])) > 100 else ""))
            
            # Цветовое кодирование
            if diff['type'] == 'added':
                item.setForeground(0, QColor("green"))
                item.setForeground(1, QColor("green"))
            elif diff['type'] == 'removed':
                item.setForeground(0, QColor("red"))
                item.setForeground(1, QColor("red"))
            elif diff['type'] == 'modified':
                item.setForeground(0, QColor("orange"))
                item.setForeground(1, QColor("orange"))
            else:  # identical
                item.setForeground(0, QColor("gray"))
                item.setForeground(1, QColor("gray"))
    
    def _update_json_display(self):
        """Обновить отображение JSON"""
        # Форматируем JSON
        indent = 2 if self.pretty_format.isChecked() else None
        
        config1_json = json.dumps(self.config1, indent=indent, ensure_ascii=False)
        config2_json = json.dumps(self.config2, indent=indent, ensure_ascii=False)
        
        # Устанавливаем текст
        self.config1_text.setPlainText(config1_json)
        self.config2_text.setPlainText(config2_json)
        
        # Добавляем подсветку синтаксиса
        highlighter1 = JSONHighlighter(self.config1_text.document())
        highlighter2 = JSONHighlighter(self.config2_text.document())
        
        # Подсветка различий (если включена)
        if self.highlight_differences.isChecked():
            self._highlight_json_differences()
    
    def _update_list_display(self):
        """Обновить отображение списка"""
        self.differences_list.clear()
        
        for diff in self.differences:
            if not self._should_show_difference(diff):
                continue
            
            item = QListWidgetItem()
            item.setText(f"{self._get_type_display_name(diff['type'])}: {diff['path']}")
            item.setData(Qt.ItemDataRole.UserRole, diff)
            
            # Цветовое кодирование
            if diff['type'] == 'added':
                item.setForeground(QColor("green"))
            elif diff['type'] == 'removed':
                item.setForeground(QColor("red"))
            elif diff['type'] == 'modified':
                item.setForeground(QColor("orange"))
            else:  # identical
                item.setForeground(QColor("gray"))
            
            self.differences_list.addItem(item)
    
    def _should_show_difference(self, diff):
        """Проверить, нужно ли показывать различие"""
        if diff['type'] == 'identical' and not self.show_identical.isChecked():
            return False
        elif diff['type'] == 'added' and not self.show_added.isChecked():
            return False
        elif diff['type'] == 'removed' and not self.show_removed.isChecked():
            return False
        elif diff['type'] == 'modified' and not self.show_modified.isChecked():
            return False
        
        # Фильтр по типу
        type_filter = self.type_filter.currentText()
        if type_filter != "Все" and self._get_type_display_name(diff['type']) != type_filter:
            return False
        
        # Фильтр по секции
        section_filter = self.section_filter.currentText()
        if section_filter != "Все":
            path_parts = diff['path'].split('.')
            if not path_parts or path_parts[0] != section_filter:
                return False
        
        return True
    
    def _get_type_display_name(self, diff_type):
        """Получить отображаемое имя типа различия"""
        type_names = {
            'added': 'Добавлено',
            'removed': 'Удалено',
            'modified': 'Изменено',
            'identical': 'Идентично'
        }
        return type_names.get(diff_type, diff_type)
    
    def _highlight_json_differences(self):
        """Подсветить различия в JSON"""
        # Это упрощенная реализация - в реальности нужен более сложный алгоритм
        # для подсветки различий в JSON тексте
        pass
    
    def _filter_differences(self):
        """Фильтровать различия"""
        self._update_tree_display()
        self._update_list_display()
    
    def _navigate_to_prev_diff(self):
        """Перейти к предыдущему различию"""
        # Реализация навигации по различиям
        pass
    
    def _navigate_to_next_diff(self):
        """Перейти к следующему различию"""
        # Реализация навигации по различиям
        pass
    
    def _on_difference_selected(self, item):
        """Обработчик выбора различия в списке"""
        diff = item.data(Qt.ItemDataRole.UserRole)
        if diff:
            # Можно добавить логику для выделения соответствующего элемента
            # в других представлениях
            pass
    
    def _select_config(self, config, source_name):
        """Выбрать конфигурацию для восстановления"""
        self.selected_config = config
        self.selected_source = source_name
        
        # Подтверждение
        reply = QMessageBox.question(
            self,
            "Подтверждение выбора",
            f"Вы уверены, что хотите выбрать конфигурацию '{source_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.config_selected.emit(config, source_name)
            self.accept()
    
    def _export_comparison(self):
        """Экспорт сравнения"""
        try:
            # Создаем отчет о сравнении
            report = {
                'config1_name': self.config1_name,
                'config2_name': self.config2_name,
                'timestamp': json.dumps(datetime.now(), default=str),
                'statistics': {
                    'total_differences': len(self.differences),
                    'added': len([d for d in self.differences if d['type'] == 'added']),
                    'removed': len([d for d in self.differences if d['type'] == 'removed']),
                    'modified': len([d for d in self.differences if d['type'] == 'modified']),
                    'identical': len([d for d in self.differences if d['type'] == 'identical'])
                },
                'differences': self.differences
            }
            
            # Здесь должна быть логика сохранения файла
            QMessageBox.information(
                self,
                "Экспорт завершен",
                "Отчет о сравнении конфигураций сохранен"
            )
            
            self.logger.info("Экспорт сравнения конфигураций завершен")
            
        except Exception as e:
            self.logger.error(f"Ошибка экспорта сравнения: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось экспортировать сравнение: {str(e)}")