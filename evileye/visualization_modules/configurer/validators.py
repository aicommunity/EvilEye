"""
Система валидации для GUI EvilEye.

Предоставляет классы валидаторов для проверки различных типов параметров
и интеграцию с PyQt виджетами для real-time валидации.
"""

import os
import re
import json
import cv2
import numpy as np
from typing import Any, Dict, List, Optional, Tuple, Union
from pathlib import Path

try:
    from PyQt6.QtWidgets import QWidget, QLineEdit, QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtGui import QColor, QPalette
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QWidget, QLineEdit, QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox
    from PyQt5.QtCore import Qt, pyqtSignal
    from PyQt5.QtGui import QColor, QPalette
    pyqt_version = 5

from ...core.logger import get_module_logger


class ValidationResult:
    """Результат валидации с информацией об ошибке"""
    
    def __init__(self, is_valid: bool, error_message: str = "", warning_message: str = ""):
        self.is_valid = is_valid
        self.error_message = error_message
        self.warning_message = warning_message
    
    def __bool__(self):
        return self.is_valid


class BaseValidator:
    """Базовый класс для всех валидаторов"""
    
    def __init__(self, field_name: str = ""):
        self.field_name = field_name
        self.logger = get_module_logger("validators")
    
    def validate(self, value: Any) -> ValidationResult:
        """Валидация значения. Переопределить в наследниках"""
        return ValidationResult(True)
    
    def get_tooltip(self) -> str:
        """Получить tooltip для поля. Переопределить в наследниках"""
        return ""


class PathValidator(BaseValidator):
    """Валидатор для путей к файлам и директориям"""
    
    def __init__(self, field_name: str = "", must_exist: bool = True, file_types: List[str] = None):
        super().__init__(field_name)
        self.must_exist = must_exist
        self.file_types = file_types or []
    
    def validate(self, value: Any) -> ValidationResult:
        if not value or not isinstance(value, str):
            return ValidationResult(False, f"{self.field_name}: Путь не может быть пустым")
        
        path = Path(value)
        
        # Проверка существования
        if self.must_exist and not path.exists():
            return ValidationResult(False, f"{self.field_name}: Файл или директория не существует: {value}")
        
        # Проверка типа файла
        if self.file_types and path.is_file():
            if not any(str(path).lower().endswith(ext.lower()) for ext in self.file_types):
                return ValidationResult(False, f"{self.field_name}: Неподдерживаемый тип файла. Ожидается: {', '.join(self.file_types)}")
        
        return ValidationResult(True)
    
    def get_tooltip(self) -> str:
        tooltip = f"Путь к {'файлу' if self.file_types else 'файлу или директории'}"
        if self.must_exist:
            tooltip += " (должен существовать)"
        if self.file_types:
            tooltip += f"\nПоддерживаемые форматы: {', '.join(self.file_types)}"
        return tooltip


class NetworkValidator(BaseValidator):
    """Валидатор для сетевых адресов и URL"""
    
    def __init__(self, field_name: str = "", check_connectivity: bool = False):
        super().__init__(field_name)
        self.check_connectivity = check_connectivity
    
    def validate(self, value: Any) -> ValidationResult:
        if not value or not isinstance(value, str):
            return ValidationResult(False, f"{self.field_name}: URL не может быть пустым")
        
        # Базовая проверка формата URL
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        if not url_pattern.match(value):
            return ValidationResult(False, f"{self.field_name}: Неверный формат URL")
        
        # Проверка доступности (опционально)
        if self.check_connectivity:
            try:
                import requests
                response = requests.head(value, timeout=5)
                if response.status_code >= 400:
                    return ValidationResult(False, f"{self.field_name}: Сервер недоступен (код {response.status_code})")
            except Exception as e:
                return ValidationResult(False, f"{self.field_name}: Не удается подключиться к серверу")
        
        return ValidationResult(True)
    
    def get_tooltip(self) -> str:
        tooltip = "URL адрес (например: http://192.168.1.100:8080/video)"
        if self.check_connectivity:
            tooltip += "\nПроверяется доступность сервера"
        return tooltip


class NumericValidator(BaseValidator):
    """Валидатор для числовых значений"""
    
    def __init__(self, field_name: str = "", min_value: float = None, max_value: float = None, 
                 integer_only: bool = False, allow_negative: bool = True):
        super().__init__(field_name)
        self.min_value = min_value
        self.max_value = max_value
        self.integer_only = integer_only
        self.allow_negative = allow_negative
    
    def validate(self, value: Any) -> ValidationResult:
        if value is None or value == "":
            return ValidationResult(False, f"{self.field_name}: Значение не может быть пустым")
        
        try:
            if self.integer_only:
                num_value = int(value)
            else:
                num_value = float(value)
        except (ValueError, TypeError):
            return ValidationResult(False, f"{self.field_name}: Неверный числовой формат")
        
        # Проверка диапазона
        if self.min_value is not None and num_value < self.min_value:
            return ValidationResult(False, f"{self.field_name}: Значение должно быть >= {self.min_value}")
        
        if self.max_value is not None and num_value > self.max_value:
            return ValidationResult(False, f"{self.field_name}: Значение должно быть <= {self.max_value}")
        
        # Проверка отрицательных значений
        if not self.allow_negative and num_value < 0:
            return ValidationResult(False, f"{self.field_name}: Значение должно быть положительным")
        
        return ValidationResult(True)
    
    def get_tooltip(self) -> str:
        tooltip = f"{'Целое число' if self.integer_only else 'Число'}"
        if self.min_value is not None or self.max_value is not None:
            range_str = ""
            if self.min_value is not None:
                range_str += f"от {self.min_value}"
            if self.max_value is not None:
                if range_str:
                    range_str += " до "
                range_str += f"{self.max_value}"
            tooltip += f" ({range_str})"
        if not self.allow_negative:
            tooltip += " (только положительные)"
        return tooltip


class ListValidator(BaseValidator):
    """Валидатор для списков значений"""
    
    def __init__(self, field_name: str = "", item_validator: BaseValidator = None, 
                 min_length: int = None, max_length: int = None, allow_empty: bool = True):
        super().__init__(field_name)
        self.item_validator = item_validator
        self.min_length = min_length
        self.max_length = max_length
        self.allow_empty = allow_empty
    
    def validate(self, value: Any) -> ValidationResult:
        if not value:
            if self.allow_empty:
                return ValidationResult(True)
            else:
                return ValidationResult(False, f"{self.field_name}: Список не может быть пустым")
        
        # Парсинг списка из строки
        try:
            if isinstance(value, str):
                # Попытка парсинга как JSON
                try:
                    parsed_list = json.loads(value)
                except json.JSONDecodeError:
                    # Попытка парсинга как Python список
                    try:
                        parsed_list = eval(value)
                    except:
                        return ValidationResult(False, f"{self.field_name}: Неверный формат списка")
            else:
                parsed_list = value
            
            if not isinstance(parsed_list, list):
                return ValidationResult(False, f"{self.field_name}: Значение должно быть списком")
            
            # Проверка длины
            if self.min_length is not None and len(parsed_list) < self.min_length:
                return ValidationResult(False, f"{self.field_name}: Список должен содержать минимум {self.min_length} элементов")
            
            if self.max_length is not None and len(parsed_list) > self.max_length:
                return ValidationResult(False, f"{self.field_name}: Список должен содержать максимум {self.max_length} элементов")
            
            # Валидация элементов
            if self.item_validator:
                for i, item in enumerate(parsed_list):
                    result = self.item_validator.validate(item)
                    if not result:
                        return ValidationResult(False, f"{self.field_name}[{i}]: {result.error_message}")
            
            return ValidationResult(True)
            
        except Exception as e:
            return ValidationResult(False, f"{self.field_name}: Ошибка парсинга списка: {str(e)}")
    
    def get_tooltip(self) -> str:
        tooltip = "Список значений в формате [1, 2, 3] или [\"a\", \"b\", \"c\"]"
        if self.min_length is not None or self.max_length is not None:
            length_str = ""
            if self.min_length is not None:
                length_str += f"от {self.min_length}"
            if self.max_length is not None:
                if length_str:
                    length_str += " до "
                length_str += f"{self.max_length}"
            tooltip += f"\nКоличество элементов: {length_str}"
        return tooltip


class JSONValidator(BaseValidator):
    """Валидатор для JSON параметров"""
    
    def __init__(self, field_name: str = "", required_keys: List[str] = None, 
                 schema: Dict[str, Any] = None):
        super().__init__(field_name)
        self.required_keys = required_keys or []
        self.schema = schema
    
    def validate(self, value: Any) -> ValidationResult:
        if not value:
            return ValidationResult(True)  # Пустые значения разрешены
        
        try:
            if isinstance(value, str):
                parsed_json = json.loads(value)
            else:
                parsed_json = value
            
            if not isinstance(parsed_json, dict):
                return ValidationResult(False, f"{self.field_name}: JSON должен быть объектом")
            
            # Проверка обязательных ключей
            for key in self.required_keys:
                if key not in parsed_json:
                    return ValidationResult(False, f"{self.field_name}: Отсутствует обязательный ключ '{key}'")
            
            # Проверка схемы (базовая)
            if self.schema:
                for key, expected_type in self.schema.items():
                    if key in parsed_json:
                        if not isinstance(parsed_json[key], expected_type):
                            return ValidationResult(False, f"{self.field_name}: Ключ '{key}' должен быть типа {expected_type.__name__}")
            
            return ValidationResult(True)
            
        except json.JSONDecodeError as e:
            return ValidationResult(False, f"{self.field_name}: Неверный JSON формат: {str(e)}")
        except Exception as e:
            return ValidationResult(False, f"{self.field_name}: Ошибка валидации JSON: {str(e)}")
    
    def get_tooltip(self) -> str:
        tooltip = "JSON объект в формате {\"ключ\": \"значение\"}"
        if self.required_keys:
            tooltip += f"\nОбязательные ключи: {', '.join(self.required_keys)}"
        return tooltip


class DatabaseValidator(BaseValidator):
    """Валидатор для параметров подключения к базе данных"""
    
    def __init__(self, field_name: str = "", test_connection: bool = False):
        super().__init__(field_name)
        self.test_connection = test_connection
    
    def validate(self, value: Any) -> ValidationResult:
        if not isinstance(value, dict):
            return ValidationResult(False, f"{self.field_name}: Параметры БД должны быть объектом")
        
        required_fields = ['host_name', 'port', 'database_name', 'user_name']
        for field in required_fields:
            if field not in value or not value[field]:
                return ValidationResult(False, f"{self.field_name}: Отсутствует обязательное поле '{field}'")
        
        # Проверка порта
        try:
            port = int(value['port'])
            if port < 1 or port > 65535:
                return ValidationResult(False, f"{self.field_name}: Порт должен быть в диапазоне 1-65535")
        except (ValueError, TypeError):
            return ValidationResult(False, f"{self.field_name}: Порт должен быть числом")
        
        # Тест подключения (опционально)
        if self.test_connection:
            try:
                import psycopg2
                conn = psycopg2.connect(
                    host=value['host_name'],
                    port=value['port'],
                    database=value['database_name'],
                    user=value['user_name'],
                    password=value.get('password', ''),
                    connect_timeout=5
                )
                conn.close()
            except Exception as e:
                return ValidationResult(False, f"{self.field_name}: Не удается подключиться к БД: {str(e)}")
        
        return ValidationResult(True)
    
    def get_tooltip(self) -> str:
        tooltip = "Параметры подключения к PostgreSQL базе данных"
        if self.test_connection:
            tooltip += "\nПроверяется подключение к серверу"
        return tooltip


class ConfigValidator(BaseValidator):
    """Валидатор для общей конфигурации"""
    
    def __init__(self, field_name: str = ""):
        super().__init__(field_name)
        self.validators = {}
    
    def add_validator(self, key: str, validator: BaseValidator):
        """Добавить валидатор для конкретного ключа"""
        self.validators[key] = validator
    
    def validate(self, value: Any) -> ValidationResult:
        if not isinstance(value, dict):
            return ValidationResult(False, f"{self.field_name}: Конфигурация должна быть объектом")
        
        errors = []
        for key, validator in self.validators.items():
            if key in value:
                result = validator.validate(value[key])
                if not result:
                    errors.append(result.error_message)
        
        if errors:
            return ValidationResult(False, "; ".join(errors))
        
        return ValidationResult(True)
    
    def get_tooltip(self) -> str:
        return "Конфигурация системы"


class ValidatedWidget(QWidget):
    """Базовый виджет с поддержкой валидации"""
    
    validation_changed = pyqtSignal(bool, str)  # is_valid, error_message
    
    def __init__(self, validator: BaseValidator = None, parent=None):
        super().__init__(parent)
        self.validator = validator
        self.is_valid = True
        self.error_message = ""
        self._setup_validation_style()
    
    def _setup_validation_style(self):
        """Настройка стилей для отображения ошибок валидации"""
        self.valid_style = ""
        self.invalid_style = "border: 2px solid red; background-color: #ffe6e6;"
    
    def validate_input(self) -> ValidationResult:
        """Выполнить валидацию"""
        if not self.validator:
            return ValidationResult(True)
        
        # Проверяем, что валидатор является объектом, а не строкой
        if not hasattr(self.validator, 'validate'):
            return ValidationResult(True)
        
        value = self.get_value()
        result = self.validator.validate(value)
        
        self.is_valid = result.is_valid
        self.error_message = result.error_message
        
        # Обновить стиль
        if hasattr(self, 'setStyleSheet'):
            if result.is_valid:
                self.setStyleSheet(self.valid_style)
            else:
                self.setStyleSheet(self.invalid_style)
        
        # Установить tooltip
        if hasattr(self, 'setToolTip'):
            if result.is_valid:
                self.setToolTip(self.validator.get_tooltip())
            else:
                self.setToolTip(f"Ошибка: {result.error_message}")
        
        # Отправить сигнал
        self.validation_changed.emit(result.is_valid, result.error_message)
        
        return result
    
    def get_value(self) -> Any:
        """Получить значение виджета. Переопределить в наследниках"""
        return None
    
    def set_validator(self, validator: BaseValidator):
        """Установить валидатор"""
        self.validator = validator
        if validator:
            self.setToolTip(validator.get_tooltip())


class ValidatedLineEdit(QLineEdit, ValidatedWidget):
    """QLineEdit с поддержкой валидации"""
    
    def __init__(self, validator: BaseValidator = None, parent=None):
        QLineEdit.__init__(self, parent)
        ValidatedWidget.__init__(self, validator, parent)
        
        # Подключить сигнал изменения текста
        self.textChanged.connect(self._on_text_changed)
    
    def _on_text_changed(self):
        """Обработчик изменения текста"""
        self.validate_input()
    
    def get_value(self) -> str:
        """Получить текст"""
        return self.text()


class ValidatedComboBox(QComboBox, ValidatedWidget):
    """QComboBox с поддержкой валидации"""
    
    def __init__(self, validator: BaseValidator = None, parent=None):
        QComboBox.__init__(self, parent)
        ValidatedWidget.__init__(self, validator, parent)
        
        # Подключить сигнал изменения выбора
        self.currentTextChanged.connect(self._on_selection_changed)
    
    def _on_selection_changed(self):
        """Обработчик изменения выбора"""
        self.validate_input()
    
    def get_value(self) -> str:
        """Получить выбранный текст"""
        return self.currentText()


class ValidatedCheckBox(QCheckBox, ValidatedWidget):
    """QCheckBox с поддержкой валидации"""
    
    def __init__(self, validator: BaseValidator = None, parent=None):
        QCheckBox.__init__(self, parent)
        ValidatedWidget.__init__(self, validator, parent)
        
        # Подключить сигнал изменения состояния
        self.stateChanged.connect(self._on_state_changed)
    
    def _on_state_changed(self):
        """Обработчик изменения состояния"""
        self.validate_input()
    
    def get_value(self) -> bool:
        """Получить состояние чекбокса"""
        return self.isChecked()


class ValidatedSpinBox(QSpinBox, ValidatedWidget):
    """QSpinBox с поддержкой валидации"""
    
    def __init__(self, validator: BaseValidator = None, parent=None):
        QSpinBox.__init__(self, parent)
        ValidatedWidget.__init__(self, validator, parent)
        
        # Подключить сигнал изменения значения
        self.valueChanged.connect(self._on_value_changed)
    
    def _on_value_changed(self, value):
        """Обработчик изменения значения"""
        self.validate_input()
    
    def get_value(self) -> int:
        """Получить значение"""
        return self.value()


class ValidatedDoubleSpinBox(QDoubleSpinBox, ValidatedWidget):
    """QDoubleSpinBox с поддержкой валидации"""
    
    def __init__(self, validator: BaseValidator = None, parent=None):
        QDoubleSpinBox.__init__(self, parent)
        ValidatedWidget.__init__(self, validator, parent)
        
        # Подключить сигнал изменения значения
        self.valueChanged.connect(self._on_value_changed)
    
    def _on_value_changed(self, value):
        """Обработчик изменения значения"""
        self.validate_input()
    
    def get_value(self) -> float:
        """Получить значение"""
        return self.value()


# Предустановленные валидаторы для часто используемых полей
class Validators:
    """Коллекция предустановленных валидаторов"""
    
    # Пути к файлам
    MODEL_PATH = PathValidator("Путь к модели", must_exist=True, file_types=['.pt', '.onnx', '.pth'])
    VIDEO_PATH = PathValidator("Путь к видео", must_exist=True, file_types=['.mp4', '.avi', '.mov', '.mkv'])
    IMAGE_PATH = PathValidator("Путь к изображению", must_exist=True, file_types=['.jpg', '.jpeg', '.png', '.bmp'])
    DIRECTORY_PATH = PathValidator("Путь к директории", must_exist=True)
    
    # Сетевые адреса
    RTSP_URL = NetworkValidator("RTSP URL", check_connectivity=False)
    HTTP_URL = NetworkValidator("HTTP URL", check_connectivity=True)
    
    # Числовые значения
    POSITIVE_INT = NumericValidator("Положительное целое число", min_value=1, integer_only=True, allow_negative=False)
    POSITIVE_FLOAT = NumericValidator("Положительное число", min_value=0.0, allow_negative=False)
    CONFIDENCE = NumericValidator("Порог уверенности", min_value=0.0, max_value=1.0, allow_negative=False)
    FPS = NumericValidator("FPS", min_value=1, max_value=120, integer_only=True, allow_negative=False)
    PORT = NumericValidator("Порт", min_value=1, max_value=65535, integer_only=True, allow_negative=False)
    
    # Списки
    SOURCE_IDS = ListValidator("ID источников", NumericValidator(integer_only=True, allow_negative=False), allow_empty=False)
    FPS_LIST = ListValidator("Список FPS", FPS, allow_empty=False)
    
    # JSON
    BOTSORT_CONFIG = JSONValidator("Конфигурация BoTSORT", 
                                  required_keys=['track_high_thresh', 'track_low_thresh', 'new_track_thresh', 'match_thresh'])
    
    # База данных
    DATABASE_CONFIG = DatabaseValidator("Конфигурация БД", test_connection=False)
