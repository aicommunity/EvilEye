"""Сервис управления pipeline."""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any, Dict, Optional

from evileye.core.interfaces import IPipeline
from evileye.core.logger import get_module_logger
from evileye.pipelines import PipelineSurveillance


class PipelineService:
    """Сервис для управления pipeline: создание, инициализация, конфигурация."""

    def __init__(self, class_manager=None):
        """Инициализация сервиса.

        Args:
            class_manager: Менеджер классов для передачи в детекторы
        """
        self.logger = get_module_logger("pipeline_service")
        self.class_manager = class_manager
        self._pipeline: Optional[IPipeline] = None

    def create_pipeline(self, pipeline_class_name: Optional[str] = None) -> IPipeline:
        """Создать экземпляр pipeline.

        Args:
            pipeline_class_name: Имя класса pipeline, если None - используется PipelineSurveillance

        Returns:
            Экземпляр pipeline

        Raises:
            ValueError: Если класс pipeline не найден
        """
        if pipeline_class_name:
            try:
                self._pipeline = self._create_pipeline_instance(pipeline_class_name)
                self.logger.info(f"Created pipeline: {pipeline_class_name}")
            except Exception as e:
                self.logger.warning(f"Failed to create pipeline '{pipeline_class_name}': {e}")
                self.logger.info("Falling back to default PipelineSurveillance")
                self._pipeline = PipelineSurveillance()
        else:
            self.logger.info("Using default PipelineSurveillance")
            self._pipeline = PipelineSurveillance()

        return self._pipeline

    def initialize_pipeline(
        self,
        pipeline: IPipeline,
        pipeline_params: Dict[str, Any],
        credentials: Optional[Dict[str, Any]] = None,
    ) -> IPipeline:
        """Инициализировать pipeline с параметрами и учетными данными.

        Args:
            pipeline: Экземпляр pipeline для инициализации
            pipeline_params: Параметры конфигурации pipeline
            credentials: Учетные данные для источников

        Returns:
            Инициализированный pipeline
        """
        if credentials:
            pipeline.set_credentials(credentials)
        pipeline.set_params(**pipeline_params)
        pipeline.init()

        # Установить ClassManager для всех детекторов
        if self.class_manager:
            self._set_class_manager_for_detectors(pipeline)

        self._pipeline = pipeline
        return pipeline

    def get_pipeline(self) -> Optional[IPipeline]:
        """Получить текущий pipeline.

        Returns:
            Текущий pipeline или None
        """
        return self._pipeline

    def start_pipeline(self) -> None:
        """Запустить pipeline."""
        if self._pipeline:
            self._pipeline.start()
            self.logger.info("Pipeline started")
        else:
            self.logger.warning("Cannot start pipeline: pipeline not initialized")

    def stop_pipeline(self) -> None:
        """Остановить pipeline."""
        if self._pipeline:
            self._pipeline.stop()
            self.logger.info("Pipeline stopped")

    def release_pipeline(self) -> None:
        """Освободить ресурсы pipeline."""
        if self._pipeline:
            self._pipeline.release()
            self._pipeline = None
            self.logger.info("Pipeline released")

    def get_sources(self) -> list:
        """Получить источники из pipeline.

        Returns:
            Список источников
        """
        if self._pipeline and hasattr(self._pipeline, "get_sources"):
            return self._pipeline.get_sources()
        return []

    def _create_pipeline_instance(self, pipeline_class_name: str) -> IPipeline:
        """Создать экземпляр pipeline по имени класса.

        Args:
            pipeline_class_name: Имя класса pipeline

        Returns:
            Экземпляр pipeline

        Raises:
            ValueError: Если класс не найден
        """
        pipeline_classes = self._discover_pipeline_classes()

        if pipeline_class_name not in pipeline_classes:
            available_classes = list(pipeline_classes.keys())
            raise ValueError(
                f"Pipeline class '{pipeline_class_name}' not found. "
                f"Available classes: {available_classes}"
            )

        pipeline_class = pipeline_classes[pipeline_class_name]
        return pipeline_class()

    def _discover_pipeline_classes(self) -> Dict[str, type]:
        """Обнаружить все доступные классы pipeline.

        Returns:
            Словарь {имя_класса: класс}
        """
        pipeline_classes = {}

        # Поиск в пакете evileye.pipelines
        try:
            pipelines_module = importlib.import_module('evileye.pipelines')
            for name, obj in inspect.getmembers(pipelines_module):
                if (inspect.isclass(obj) and
                    hasattr(obj, '__bases__') and
                    any('Pipeline' in base.__name__ for base in obj.__bases__)):
                    pipeline_classes[name] = obj
        except ImportError as e:
            self.logger.warning(f"Failed to import evileye.pipelines: {e}")

        # Поиск в локальной директории pipelines
        current_dir = Path.cwd()
        pipelines_dir = current_dir / "pipelines"
        if pipelines_dir.exists() and pipelines_dir.is_dir():
            try:
                import sys
                sys.path.insert(0, str(current_dir))

                pipelines_module = importlib.import_module('pipelines')
                for name, obj in inspect.getmembers(pipelines_module):
                    if (inspect.isclass(obj) and
                        hasattr(obj, '__bases__') and
                        any('Pipeline' in base.__name__ for base in obj.__bases__)):
                        pipeline_classes[name] = obj

                sys.path.pop(0)
            except ImportError as e:
                self.logger.warning(f"Failed to import local pipelines: {e}")

        return pipeline_classes

    def _set_class_manager_for_detectors(self, pipeline: IPipeline) -> None:
        """Установить ClassManager для всех детекторов в pipeline.

        Args:
            pipeline: Pipeline для установки ClassManager
        """
        try:
            if hasattr(pipeline, 'processors'):
                for processor in pipeline.processors:
                    if hasattr(processor, 'get_processors'):
                        for proc in processor.get_processors():
                            if hasattr(proc, 'set_class_manager'):
                                proc.set_class_manager(self.class_manager)
        except Exception as e:
            self.logger.warning(f"Failed to set class manager for detectors: {e}")

    def get_available_pipeline_classes(self) -> list[str]:
        """Получить список доступных классов pipeline.

        Returns:
            Список имен классов
        """
        return list(self._discover_pipeline_classes().keys())
