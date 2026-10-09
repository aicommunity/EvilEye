"""Сервис управления pipeline."""

from __future__ import annotations

from typing import Any, Dict, Optional

from evileye.core.contracts import PipelineConfig, PipelineDependencies
from evileye.core.interfaces import IPipeline
from evileye.core.logger import get_module_logger
from evileye.core.plugins import plugin_manager, plugin_registry


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

    def create_pipeline(
        self,
        pipeline_class_name: Optional[str] = None,
        pipeline_params: Optional[Dict[str, Any]] = None,
        credentials: Optional[Dict[str, Any]] = None,
    ) -> IPipeline:
        """Создать экземпляр pipeline.

        Args:
            pipeline_class_name: Имя класса pipeline, если None - используется PipelineSurveillance

        Returns:
            Экземпляр pipeline (соответствует IPipeline Protocol)

        Raises:
            ValueError: Если класс pipeline не найден
        """
        selected = pipeline_class_name or "PipelineSurveillance"
        self._pipeline = self._create_pipeline_instance(
            selected,
            pipeline_params=pipeline_params or {},
            credentials=credentials,
        )
        self.logger.info("Created pipeline: %s", selected)

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

    def _create_pipeline_instance(
        self,
        pipeline_class_name: str,
        *,
        pipeline_params: Optional[Dict[str, Any]] = None,
        credentials: Optional[Dict[str, Any]] = None,
    ) -> IPipeline:
        """Создать экземпляр pipeline по имени класса.

        Args:
            pipeline_class_name: Имя класса pipeline

        Returns:
            Экземпляр pipeline

        Raises:
            ValueError: Если класс не найден
        """
        self._register_builtin_pipelines()
        plugin_manager.load()
        registered = plugin_registry.get_pipeline(pipeline_class_name)
        if registered is None:
            available_classes = self.get_available_pipeline_classes()
            raise ValueError(
                f"Pipeline class '{pipeline_class_name}' not found. "
                f"Available classes: {available_classes}"
            )

        dependencies = PipelineDependencies(
            config=PipelineConfig(
                raw_config=dict(pipeline_params or {}),
                credentials=dict(credentials or {}) if credentials is not None else None,
            )
        )
        pipeline = registered.spec.factory(dependencies)
        required_methods = (
            "init", "start", "stop", "reset", "set_params", "get_params",
            "set_credentials", "get_credentials", "process", "get_sources",
            "get_results_list", "get_current_results",
        )
        missing = [method for method in required_methods if not callable(getattr(pipeline, method, None))]
        if missing:
            raise TypeError(
                f"Pipeline '{pipeline_class_name}' does not implement IPipeline; "
                f"missing methods: {', '.join(missing)}"
            )
        return pipeline

    @staticmethod
    def _register_builtin_pipelines() -> None:
        from evileye.pipelines.pipeline_capture import PipelineCapture
        from evileye.pipelines.pipeline_declarative import PipelineDeclarative
        from evileye.pipelines.pipeline_surveillance import PipelineSurveillance

        for pipeline_class in (PipelineSurveillance, PipelineCapture, PipelineDeclarative):
            canonical = f"evileye/{pipeline_class.__name__}"
            if plugin_registry.get_pipeline(canonical) is None:
                plugin_registry.register_builtin_pipeline(
                    pipeline_class.__name__,
                    lambda _dependencies, cls=pipeline_class: cls(),
                )

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
        self._register_builtin_pipelines()
        plugin_manager.load()
        return plugin_registry.list_pipeline_names()

    def _discover_pipeline_classes(self) -> Dict[str, type]:
        """Compatibility helper returning registered pipeline factories."""
        self._register_builtin_pipelines()
        plugin_manager.load()
        return {
            name: registered.spec.factory
            for name in plugin_registry.list_pipeline_names()
            if (registered := plugin_registry.get_pipeline(name)) is not None
        }
