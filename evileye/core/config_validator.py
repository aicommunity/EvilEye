"""Валидация конфигураций с использованием pydantic."""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from pydantic import BaseModel, Field, ValidationError, field_validator

    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseModel = object
    Field = None
    ValidationError = Exception
    field_validator = None

if PYDANTIC_AVAILABLE:
    class PipelineConfigModel(BaseModel):
        """Модель валидации конфигурации pipeline."""

        pipeline_class: Optional[str] = Field(default=None, description="Класс pipeline")
        sources: list = Field(default_factory=list, description="Источники видео")
        detectors: list = Field(default_factory=list, description="Детекторы объектов")
        trackers: list = Field(default_factory=list, description="Трекеры объектов")


    class DatabaseConfigModel(BaseModel):
        """Модель валидации конфигурации БД."""

        database_name: str = Field(default="evil_eye_db", description="Имя базы данных")
        host_name: str = Field(default="localhost", description="Хост БД")
        port: int = Field(default=5432, ge=1, le=65535, description="Порт БД")
        image_dir: str = Field(default="EvilEyeData", description="Директория для изображений")


    class ControllerConfigModel(BaseModel):
        """Модель валидации конфигурации контроллера."""

        fps: int = Field(default=30, ge=1, le=120, description="FPS обработки")
        show_main_gui: bool = Field(default=True, description="Показывать главное GUI")
        use_database: bool = Field(default=False, description="Использовать БД")


class ConfigValidator:
    """Валидатор конфигураций."""

    def __init__(self):
        """Инициализация валидатора."""
        self._pydantic_available = PYDANTIC_AVAILABLE

    def validate_pipeline_config(self, config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Валидировать конфигурацию pipeline.

        Args:
            config: Конфигурация для валидации

        Returns:
            Кортеж (успех, сообщение_об_ошибке)
        """
        if not self._pydantic_available:
            # Базовая валидация без pydantic
            if not isinstance(config, dict):
                return False, "Pipeline config must be a dictionary"
            return True, None

        try:
            PipelineConfigModel(**config)
            return True, None
        except ValidationError as e:
            return False, str(e)

    def validate_database_config(self, config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Валидировать конфигурацию БД.

        Args:
            config: Конфигурация для валидации

        Returns:
            Кортеж (успех, сообщение_об_ошибке)
        """
        if not self._pydantic_available:
            # Базовая валидация без pydantic
            if not isinstance(config, dict):
                return False, "Database config must be a dictionary"
            return True, None

        try:
            DatabaseConfigModel(**config)
            return True, None
        except ValidationError as e:
            return False, str(e)

    def validate_controller_config(self, config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Валидировать конфигурацию контроллера.

        Args:
            config: Конфигурация для валидации

        Returns:
            Кортеж (успех, сообщение_об_ошибке)
        """
        if not self._pydantic_available:
            # Базовая валидация без pydantic
            if not isinstance(config, dict):
                return False, "Controller config must be a dictionary"
            return True, None

        try:
            ControllerConfigModel(**config)
            return True, None
        except ValidationError as e:
            return False, str(e)

    def validate_full_config(self, config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Валидировать полную конфигурацию системы.

        Args:
            config: Полная конфигурация

        Returns:
            Кортеж (успех, сообщение_об_ошибке)
        """
        if not isinstance(config, dict):
            return False, "Config must be a dictionary"

        # Валидация секций
        if 'pipeline' in config:
            success, error = self.validate_pipeline_config(config['pipeline'])
            if not success:
                return False, f"Pipeline config error: {error}"

        if 'database' in config:
            success, error = self.validate_database_config(config['database'])
            if not success:
                return False, f"Database config error: {error}"

        if 'controller' in config:
            success, error = self.validate_controller_config(config['controller'])
            if not success:
                return False, f"Controller config error: {error}"

        return True, None
