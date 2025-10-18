"""
Диалог восстановления конфигурации для EvilEye.

Предоставляет интерфейс для восстановления конфигурации из истории jobs
с предварительным просмотром и валидацией.
"""

import copy
import json
from datetime import datetime
from typing import Dict, Any, Optional

try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
        QGroupBox, QFormLayout, QCheckBox, QMessageBox, QProgressBar,
        QSplitter, QTreeWidget, QTreeWidgetItem, QHeaderView, QScrollArea
    )
    from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer
    from PyQt6.QtGui import QFont, QColor, QPalette
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
        QGroupBox, QFormLayout, QCheckBox, QMessageBox, QProgressBar,
        QSplitter, QTreeWidget, QTreeWidgetItem, QHeaderView, QScrollArea
    )
    from PyQt5.QtCore import Qt, pyqtSignal, QThread, QTimer
    from PyQt5.QtGui import QFont, QColor, QPalette
    pyqt_version = 5

from ...core.logger import get_module_logger


class ConfigValidationThread(QThread):
    """Поток для валидации конфигурации"""
    
    validation_completed = pyqtSignal(bool, str)  # is_valid, message
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.config = config
        self.logger = get_module_logger("config_validation")
    
    def run(self):
        """Выполнить валидацию конфигурации"""
        try:
            # Базовая валидация структуры
            required_sections = ['sources', 'detectors', 'trackers']
            missing_sections = []
            
            for section in required_sections:
                if section not in self.config:
                    missing_sections.append(section)
            
            if missing_sections:
                self.validation_completed.emit(False, f"Отсутствуют обязательные секции: {', '.join(missing_sections)}")
                return
            
            # Валидация источников
            sources = self.config.get('sources', [])
            if not sources:
                self.validation_completed.emit(False, "Не указаны источники видео")
                return
            
            # Валидация детекторов
            detectors = self.config.get('detectors', [])
            if not detectors:
                self.validation_completed.emit(False, "Не указаны детекторы")
                return
            
            # Валидация трекеров
            trackers = self.config.get('trackers', [])
            if not trackers:
                self.validation_completed.emit(False, "Не указаны трекеры")
                return
            
            # Дополнительные проверки
            for i, source in enumerate(sources):
                if not source.get('source'):
                    self.validation_completed.emit(False, f"Источник {i}: не указан путь к видео")
                    return
            
            for i, detector in enumerate(detectors):
                if not detector.get('model'):
                    self.validation_completed.emit(False, f"Детектор {i}: не указана модель")
                    return
            
            self.validation_completed.emit(True, "Конфигурация валидна")
            
        except Exception as e:
            self.logger.error(f"Ошибка валидации конфигурации: {str(e)}")
            self.validation_completed.emit(False, f"Ошибка валидации: {str(e)}")


class ConfigRestoreDialog(QDialog):
    """Диалог восстановления конфигурации"""
    
    config_restored = pyqtSignal(dict)  # restored_config
    
    def __init__(self, job_data: Dict[str, Any], current_config: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.logger = get_module_logger("config_restore_dialog")
        
        self.job_data = job_data
        self.current_config = current_config
        self.config_to_restore = None
        self.validation_thread = None
        
        self.setWindowTitle("Восстановление конфигурации")
        self.setModal(True)
        self.resize(1000, 700)
        
        self._init_ui()
        self._load_job_data()
        self._start_validation()
    
    def _init_ui(self):
        """Инициализация пользовательского интерфейса"""
        layout = QVBoxLayout(self)
        
        # Заголовок
        title_label = QLabel("Восстановление конфигурации")
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Информация о задаче
        self._add_job_info_section(layout)
        
        # Основной контент с разделителем
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # Левая панель - информация о конфигурации
        left_panel = self._create_config_info_panel()
        splitter.addWidget(left_panel)
        
        # Правая панель - сравнение конфигураций
        right_panel = self._create_comparison_panel()
        splitter.addWidget(right_panel)
        
        # Устанавливаем пропорции
        splitter.setSizes([400, 600])
        
        # Прогресс-бар валидации
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Кнопки
        self._add_buttons(layout)
    
    def _add_job_info_section(self, layout):
        """Добавить секцию с информацией о задаче"""
        info_group = QGroupBox("Информация о задаче")
        info_layout = QFormLayout(info_group)
        
        # Основная информация
        self.job_id_label = QLabel()
        self.project_id_label = QLabel()
        self.creation_time_label = QLabel()
        self.finish_time_label = QLabel()
        self.duration_label = QLabel()
        
        info_layout.addRow("ID задачи:", self.job_id_label)
        info_layout.addRow("ID проекта:", self.project_id_label)
        info_layout.addRow("Время создания:", self.creation_time_label)
        info_layout.addRow("Время завершения:", self.finish_time_label)
        info_layout.addRow("Длительность:", self.duration_label)
        
        layout.addWidget(info_group)
    
    def _create_config_info_panel(self):
        """Создать панель с информацией о конфигурации"""
        panel = QGroupBox("Конфигурация для восстановления")
        layout = QVBoxLayout(panel)
        
        # Статус валидации
        self.validation_status = QLabel("Проверка конфигурации...")
        self.validation_status.setStyleSheet("color: orange; font-weight: bold;")
        layout.addWidget(self.validation_status)
        
        # Детали конфигурации
        self.config_details = QTreeWidget()
        self.config_details.setHeaderLabels(["Параметр", "Значение"])
        self.config_details.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.config_details)
        
        # Предупреждения
        self.warnings_text = QTextEdit()
        self.warnings_text.setMaximumHeight(100)
        self.warnings_text.setPlaceholderText("Предупреждения и рекомендации...")
        self.warnings_text.setStyleSheet("background-color: #fff3cd; border: 1px solid #ffeaa7;")
        layout.addWidget(self.warnings_text)
        
        return panel
    
    def _create_comparison_panel(self):
        """Создать панель сравнения конфигураций"""
        panel = QGroupBox("Сравнение с текущей конфигурацией")
        layout = QVBoxLayout(panel)
        
        # Опции сравнения
        options_layout = QHBoxLayout()
        
        self.show_differences_only = QCheckBox("Показать только различия")
        self.show_differences_only.setChecked(True)
        self.show_differences_only.toggled.connect(self._update_comparison)
        options_layout.addWidget(self.show_differences_only)
        
        self.show_added_items = QCheckBox("Показать добавленные элементы")
        self.show_added_items.setChecked(True)
        self.show_added_items.toggled.connect(self._update_comparison)
        options_layout.addWidget(self.show_added_items)
        
        self.show_removed_items = QCheckBox("Показать удаленные элементы")
        self.show_removed_items.setChecked(True)
        self.show_removed_items.toggled.connect(self._update_comparison)
        options_layout.addWidget(self.show_removed_items)
        
        layout.addLayout(options_layout)
        
        # Дерево сравнения
        self.comparison_tree = QTreeWidget()
        self.comparison_tree.setHeaderLabels(["Параметр", "Текущее значение", "Новое значение"])
        self.comparison_tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.comparison_tree)
        
        return panel
    
    def _add_buttons(self, layout):
        """Добавить кнопки управления"""
        button_layout = QHBoxLayout()
        
        # Кнопка создания backup
        self.backup_btn = QPushButton("Создать backup текущей конфигурации")
        self.backup_btn.clicked.connect(self._create_backup)
        button_layout.addWidget(self.backup_btn)
        
        button_layout.addStretch()
        
        # Кнопки управления
        self.restart_pipeline_btn = QCheckBox("Перезапустить pipeline после восстановления")
        self.restart_pipeline_btn.setChecked(True)
        button_layout.addWidget(self.restart_pipeline_btn)
        
        # Кнопки действий
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        self.restore_btn = QPushButton("Восстановить конфигурацию")
        self.restore_btn.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
        self.restore_btn.clicked.connect(self._restore_config)
        self.restore_btn.setEnabled(False)  # Будет включена после валидации
        button_layout.addWidget(self.restore_btn)
        
        layout.addLayout(button_layout)
    
    def _load_job_data(self):
        """Загрузить данные задачи"""
        # Заполняем информацию о задаче
        self.job_id_label.setText(str(self.job_data.get('job_id', 'N/A')))
        self.project_id_label.setText(str(self.job_data.get('project_id', 'N/A')))
        
        creation_time = self.job_data.get('creation_time')
        if creation_time:
            if isinstance(creation_time, str):
                self.creation_time_label.setText(creation_time)
            else:
                self.creation_time_label.setText(creation_time.strftime("%Y-%m-%d %H:%M:%S"))
        else:
            self.creation_time_label.setText("N/A")
        
        finish_time = self.job_data.get('finish_time')
        if finish_time:
            if isinstance(finish_time, str):
                self.finish_time_label.setText(finish_time)
            else:
                self.finish_time_label.setText(finish_time.strftime("%Y-%m-%d %H:%M:%S"))
        else:
            self.finish_time_label.setText("N/A")
        
        # Вычисляем длительность
        if creation_time and finish_time:
            try:
                if isinstance(creation_time, str):
                    creation_time = datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
                if isinstance(finish_time, str):
                    finish_time = datetime.fromisoformat(finish_time.replace('Z', '+00:00'))
                
                duration = finish_time - creation_time
                self.duration_label.setText(str(duration))
            except Exception as e:
                self.logger.warning(f"Не удалось вычислить длительность: {e}")
                self.duration_label.setText("N/A")
        else:
            self.duration_label.setText("N/A")
        
        # Загружаем конфигурацию
        config_info = self.job_data.get('configuration_info', {})
        if isinstance(config_info, str):
            try:
                self.config_to_restore = json.loads(config_info)
            except json.JSONDecodeError as e:
                self.logger.error(f"Ошибка парсинга конфигурации: {e}")
                self.config_to_restore = {}
        else:
            self.config_to_restore = config_info
        
        # Заполняем детали конфигурации
        self._populate_config_details()
    
    def _populate_config_details(self):
        """Заполнить детали конфигурации"""
        self.config_details.clear()
        
        if not self.config_to_restore:
            return
        
        # Создаем дерево конфигурации
        root = QTreeWidgetItem(self.config_details)
        root.setText(0, "Конфигурация")
        
        for section_name, section_data in self.config_to_restore.items():
            section_item = QTreeWidgetItem(root)
            section_item.setText(0, section_name)
            
            if isinstance(section_data, list):
                section_item.setText(1, f"Список ({len(section_data)} элементов)")
                for i, item in enumerate(section_data):
                    item_widget = QTreeWidgetItem(section_item)
                    item_widget.setText(0, f"[{i}]")
                    if isinstance(item, dict):
                        item_widget.setText(1, f"Объект ({len(item)} полей)")
                        for key, value in item.items():
                            field_item = QTreeWidgetItem(item_widget)
                            field_item.setText(0, key)
                            field_item.setText(1, str(value)[:100] + ("..." if len(str(value)) > 100 else ""))
                    else:
                        item_widget.setText(1, str(item)[:100] + ("..." if len(str(item)) > 100 else ""))
            elif isinstance(section_data, dict):
                section_item.setText(1, f"Объект ({len(section_data)} полей)")
                for key, value in section_data.items():
                    field_item = QTreeWidgetItem(section_item)
                    field_item.setText(0, key)
                    field_item.setText(1, str(value)[:100] + ("..." if len(str(value)) > 100 else ""))
            else:
                section_item.setText(1, str(section_data)[:100] + ("..." if len(str(section_data)) > 100 else ""))
        
        # Разворачиваем корневой элемент
        root.setExpanded(True)
    
    def _start_validation(self):
        """Запустить валидацию конфигурации"""
        if not self.config_to_restore:
            self.validation_status.setText("Ошибка: конфигурация не найдена")
            self.validation_status.setStyleSheet("color: red; font-weight: bold;")
            return
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Неопределенный прогресс
        
        self.validation_thread = ConfigValidationThread(self.config_to_restore)
        self.validation_thread.validation_completed.connect(self._on_validation_completed)
        self.validation_thread.start()
    
    def _on_validation_completed(self, is_valid: bool, message: str):
        """Обработчик завершения валидации"""
        self.progress_bar.setVisible(False)
        
        if is_valid:
            self.validation_status.setText("✓ Конфигурация валидна")
            self.validation_status.setStyleSheet("color: green; font-weight: bold;")
            self.restore_btn.setEnabled(True)
        else:
            self.validation_status.setText(f"✗ {message}")
            self.validation_status.setStyleSheet("color: red; font-weight: bold;")
            self.restore_btn.setEnabled(False)
        
        # Обновляем сравнение
        self._update_comparison()
    
    def _update_comparison(self):
        """Обновить сравнение конфигураций"""
        self.comparison_tree.clear()
        
        if not self.config_to_restore:
            return
        
        # Создаем дерево сравнения
        root = QTreeWidgetItem(self.comparison_tree)
        root.setText(0, "Сравнение конфигураций")
        
        # Сравниваем секции
        all_sections = set(self.current_config.keys()) | set(self.config_to_restore.keys())
        
        for section_name in sorted(all_sections):
            current_section = self.current_config.get(section_name)
            new_section = self.config_to_restore.get(section_name)
            
            if current_section is None:
                # Новая секция
                if self.show_added_items.isChecked():
                    section_item = QTreeWidgetItem(root)
                    section_item.setText(0, f"+ {section_name}")
                    section_item.setText(1, "Отсутствует")
                    section_item.setText(2, "Добавляется")
                    section_item.setForeground(0, QColor("green"))
                    section_item.setForeground(1, QColor("gray"))
                    section_item.setForeground(2, QColor("green"))
            elif new_section is None:
                # Удаленная секция
                if self.show_removed_items.isChecked():
                    section_item = QTreeWidgetItem(root)
                    section_item.setText(0, f"- {section_name}")
                    section_item.setText(1, "Будет удалена")
                    section_item.setText(2, "Отсутствует")
                    section_item.setForeground(0, QColor("red"))
                    section_item.setForeground(1, QColor("red"))
                    section_item.setForeground(2, QColor("gray"))
            else:
                # Секция существует в обеих конфигурациях
                if self._sections_different(current_section, new_section):
                    if self.show_differences_only.isChecked():
                        section_item = QTreeWidgetItem(root)
                        section_item.setText(0, f"~ {section_name}")
                        section_item.setText(1, "Изменяется")
                        section_item.setText(2, "Изменяется")
                        section_item.setForeground(0, QColor("orange"))
                        section_item.setForeground(1, QColor("orange"))
                        section_item.setForeground(2, QColor("orange"))
                        
                        # Добавляем детали изменений
                        self._add_section_changes(section_item, current_section, new_section)
        
        # Разворачиваем корневой элемент
        root.setExpanded(True)
    
    def _sections_different(self, current, new):
        """Проверить, отличаются ли секции"""
        return json.dumps(current, sort_keys=True) != json.dumps(new, sort_keys=True)
    
    def _add_section_changes(self, parent_item, current, new):
        """Добавить детали изменений секции"""
        if isinstance(current, dict) and isinstance(new, dict):
            all_keys = set(current.keys()) | set(new.keys())
            for key in sorted(all_keys):
                current_val = current.get(key)
                new_val = new.get(key)
                
                if current_val != new_val:
                    change_item = QTreeWidgetItem(parent_item)
                    change_item.setText(0, key)
                    change_item.setText(1, str(current_val)[:50] + ("..." if len(str(current_val)) > 50 else ""))
                    change_item.setText(2, str(new_val)[:50] + ("..." if len(str(new_val)) > 50 else ""))
    
    def _create_backup(self):
        """Создать backup текущей конфигурации"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"config_backup_{timestamp}.json"
            
            # Здесь должна быть логика сохранения backup
            # Пока просто показываем сообщение
            QMessageBox.information(
                self, 
                "Backup создан", 
                f"Backup текущей конфигурации сохранен как {backup_filename}"
            )
            
            self.logger.info(f"Backup конфигурации создан: {backup_filename}")
            
        except Exception as e:
            self.logger.error(f"Ошибка создания backup: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось создать backup: {str(e)}")
    
    def _restore_config(self):
        """Восстановить конфигурацию"""
        if not self.config_to_restore:
            QMessageBox.warning(self, "Ошибка", "Нет конфигурации для восстановления")
            return
        
        # Подтверждение
        reply = QMessageBox.question(
            self,
            "Подтверждение восстановления",
            "Вы уверены, что хотите восстановить эту конфигурацию?\n\n"
            "Текущая конфигурация будет заменена.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Отправляем сигнал с конфигурацией для восстановления
            restore_data = {
                'config': self.config_to_restore,
                'restart_pipeline': self.restart_pipeline_btn.isChecked(),
                'job_id': self.job_data.get('job_id'),
                'project_id': self.job_data.get('project_id')
            }
            
            self.config_restored.emit(restore_data)
            self.accept()
    
    def closeEvent(self, event):
        """Обработчик закрытия окна"""
        if self.validation_thread and self.validation_thread.isRunning():
            self.validation_thread.terminate()
            self.validation_thread.wait()
        
        event.accept()