"""
Базовый класс для вкладок конфигуратора EvilEye.

Предоставляет общую функциональность для всех вкладок:
- Валидация параметров
- Обработка изменений
- Генерация tooltips
- Управление состоянием
"""

import copy
from typing import Any, Dict, List, Optional, Union

try:
    from PyQt6.QtWidgets import QWidget, QGroupBox, QVBoxLayout, QHBoxLayout, QFormLayout, QPushButton, QLabel, QSizePolicy
    from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
    from PyQt6.QtGui import QFont
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QWidget, QGroupBox, QVBoxLayout, QHBoxLayout, QFormLayout, QPushButton, QLabel, QSizePolicy
    from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
    from PyQt5.QtGui import QFont
    pyqt_version = 5

from ..validators import BaseValidator, ValidationResult, ValidatedWidget
from ....core.logger import get_module_logger


class BaseTab(QWidget):
    """Базовый класс для всех вкладок конфигуратора"""
    
    # Сигналы
    config_changed = pyqtSignal()  # Изменение конфигурации
    validation_failed = pyqtSignal(str)  # Ошибка валидации (сообщение)
    validation_passed = pyqtSignal()  # Валидация прошла успешно
    
    def __init__(self, config_params: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.logger = get_module_logger("base_tab")
        
        # Параметры конфигурации
        self.params = config_params
        self.config_result = copy.deepcopy(config_params)
        
        # Валидаторы для полей
        self.validators: Dict[str, BaseValidator] = {}
        self.validated_widgets: Dict[str, ValidatedWidget] = {}
        
        # Состояние валидации
        self.validation_errors: List[str] = []
        self.is_valid = True
        
        # Инициализация UI
        self._init_ui()
        self._setup_validators()
        self._connect_signals()
    
    def _init_ui(self):
        """Инициализация пользовательского интерфейса. Переопределить в наследниках"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)
        
        # Устанавливаем политику размеров для правильного заполнения пространства
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    
    def _setup_validators(self):
        """Настройка валидаторов. Переопределить в наследниках"""
        pass
    
    def _connect_signals(self):
        """Подключение сигналов. Переопределить в наследниках"""
        pass
    
    def add_group_box(self, title: str, layout: QFormLayout) -> QGroupBox:
        """Добавить группу полей с заголовком"""
        group_box = QGroupBox(title)
        group_box.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.main_layout.addWidget(group_box)
        return group_box
    
    def add_validated_widget(self, field_name: str, widget: ValidatedWidget, validator: BaseValidator = None):
        """Добавить виджет с валидацией"""
        if validator:
            widget.set_validator(validator)
            self.validators[field_name] = validator
        
        self.validated_widgets[field_name] = widget
        
        # Подключить сигнал валидации (временно отключено из-за проблем с PyQt6)
        # widget.validation_changed.connect(self._on_validation_changed)
    
    @pyqtSlot()
    def _on_validation_changed(self, is_valid, error_message):
        """Обработчик изменения валидации"""
        sender = self.sender()
        
        # Найти поле по виджету
        field_name = None
        for name, widget in self.validated_widgets.items():
            if widget == sender:
                field_name = name
                break
        
        if field_name:
            if is_valid:
                # Удалить ошибку из списка
                if field_name in self.validation_errors:
                    self.validation_errors.remove(field_name)
            else:
                # Добавить ошибку в список
                if field_name not in self.validation_errors:
                    self.validation_errors.append(field_name)
            
            # Обновить общее состояние валидации
            self.is_valid = len(self.validation_errors) == 0
            
            # Отправить сигналы
            if self.is_valid:
                self.validation_passed.emit()
            else:
                self.validation_failed.emit(f"Ошибки в полях: {', '.join(self.validation_errors)}")
    
    def validate_all(self) -> ValidationResult:
        """Валидация всех полей"""
        errors = []
        
        for field_name, widget in self.validated_widgets.items():
            result = widget.validate_input()
            if not result:
                errors.append(f"{field_name}: {result.error_message}")
        
        if errors:
            return ValidationResult(False, "; ".join(errors))
        
        return ValidationResult(True)
    
    def get_params(self) -> Dict[str, Any]:
        """Получить параметры конфигурации. Переопределить в наследниках"""
        return self.config_result
    
    def set_params(self, params: Dict[str, Any]):
        """Установить параметры конфигурации. Переопределить в наследниках"""
        self.params = params
        self.config_result = copy.deepcopy(params)
        self._update_ui_from_params()
    
    def _update_ui_from_params(self):
        """Обновить UI из параметров. Переопределить в наследниках"""
        pass
    
    def _on_config_changed(self):
        """Обработчик изменения конфигурации"""
        self.config_changed.emit()
    
    def add_validate_button(self) -> QPushButton:
        """Добавить кнопку валидации"""
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        validate_button = QPushButton("Проверить все параметры")
        validate_button.setMinimumWidth(200)
        validate_button.clicked.connect(self._on_validate_button_clicked)
        button_layout.addWidget(validate_button)
        
        self.main_layout.addLayout(button_layout)
        return validate_button
    
    @pyqtSlot()
    def _on_validate_button_clicked(self):
        """Обработчик нажатия кнопки валидации"""
        result = self.validate_all()
        if result:
            self.logger.info("Валидация прошла успешно")
            # Можно показать сообщение об успехе
        else:
            self.logger.error(f"Ошибки валидации: {result.error_message}")
            # Можно показать диалог с ошибками
    
    def get_tooltip_for_field(self, field_name: str, description: str, 
                            range_info: str = "", example: str = "") -> str:
        """Генерация tooltip для поля"""
        tooltip = description
        if range_info:
            tooltip += f"\nДиапазон: {range_info}"
        if example:
            tooltip += f"\nПример: {example}"
        return tooltip
    
    def create_form_layout(self) -> QFormLayout:
        """Создать новый FormLayout"""
        layout = QFormLayout()
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.setSpacing(10)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        return layout
    
    def add_section_separator(self, title: str = ""):
        """Добавить разделитель секции"""
        if title:
            separator_label = QLabel(title)
            separator_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            separator_label.setStyleSheet("color: #2c3e50; margin: 10px 0px;")
            self.main_layout.addWidget(separator_label)
        else:
            # Простая линия-разделитель
            line = QLabel("─" * 50)
            line.setStyleSheet("color: #bdc3c7;")
            line.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.main_layout.addWidget(line)
    
    def add_stretch(self):
        """Добавить растягивающийся элемент"""
        self.main_layout.addStretch()
    
    def get_validation_status(self) -> Dict[str, Any]:
        """Получить статус валидации"""
        return {
            'is_valid': self.is_valid,
            'errors': self.validation_errors.copy(),
            'error_count': len(self.validation_errors)
        }
    
    def clear_validation_errors(self):
        """Очистить ошибки валидации"""
        self.validation_errors.clear()
        self.is_valid = True
        
        # Сбросить стили всех виджетов
        for widget in self.validated_widgets.values():
            if hasattr(widget, 'setStyleSheet'):
                widget.setStyleSheet("")
    
    def set_field_enabled(self, field_name: str, enabled: bool):
        """Включить/выключить поле"""
        if field_name in self.validated_widgets:
            widget = self.validated_widgets[field_name]
            if hasattr(widget, 'setEnabled'):
                widget.setEnabled(enabled)
    
    def get_field_value(self, field_name: str) -> Any:
        """Получить значение поля"""
        if field_name in self.validated_widgets:
            return self.validated_widgets[field_name].get_value()
        return None
    
    def set_field_value(self, field_name: str, value: Any):
        """Установить значение поля"""
        if field_name in self.validated_widgets:
            widget = self.validated_widgets[field_name]
            if hasattr(widget, 'setText'):
                widget.setText(str(value))
            elif hasattr(widget, 'setValue'):
                widget.setValue(value)
            elif hasattr(widget, 'setChecked'):
                widget.setChecked(bool(value))
    
    def add_help_text(self, text: str):
        """Добавить текст помощи"""
        help_label = QLabel(text)
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: #7f8c8d; font-style: italic; padding: 5px;")
        self.main_layout.addWidget(help_label)
