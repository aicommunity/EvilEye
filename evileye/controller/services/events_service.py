"""Сервис управления детекторами событий и их обработкой."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from evileye.core.interfaces import IEventDetector, IObjectHandler, IPipeline
from evileye.core.logger import get_module_logger
from evileye.events_control.events_controller import EventsDetectorsController
from evileye.events_control.events_processor import EventsProcessor
from evileye.events_detectors.attribute_events_detector import AttributeEventsDetector
from evileye.events_detectors.cam_events_detector import CamEventsDetector
from evileye.events_detectors.fov_events_detector import FieldOfViewEventsDetector
from evileye.events_detectors.system_events_detector import SystemEventsDetector
from evileye.events_detectors.zone_events_detector import ZoneEventsDetector


class EventsService:
    """Сервис для управления детекторами событий и их обработкой."""

    def __init__(self):
        """Инициализация сервиса."""
        self.logger = get_module_logger("events_service")
        self._detectors: Dict[str, IEventDetector] = {}
        self._detectors_controller: Optional[EventsDetectorsController] = None
        self._events_processor: Optional[EventsProcessor] = None

    def initialize_detectors(
        self,
        params: Dict[str, Any],
        pipeline: IPipeline,
        objects_handler: IObjectHandler,
        use_database: bool = True,
    ) -> None:
        """Инициализировать детекторы событий.

        Args:
            params: Параметры конфигурации детекторов
            pipeline: Pipeline для получения источников (соответствует IPipeline)
            objects_handler: Обработчик объектов для подписки (соответствует IObjectHandler)
            use_database: Использовать ли БД (влияет на инициализацию)
        """
        # Protocol compliance: IPipeline гарантирует наличие метода get_sources()
        # CamEventsDetector
        sources = pipeline.get_sources()
        self._detectors['CamEventsDetector'] = CamEventsDetector(sources)
        self._detectors['CamEventsDetector'].set_params(**params.get('CamEventsDetector', {}))
        self._detectors['CamEventsDetector'].init()

        # FieldOfViewEventsDetector
        self._detectors['FieldOfViewEventsDetector'] = FieldOfViewEventsDetector(objects_handler)
        self._detectors['FieldOfViewEventsDetector'].set_params(**params.get('FieldOfViewEventsDetector', {}))
        self._detectors['FieldOfViewEventsDetector'].init()

        # ZoneEventsDetector
        self._detectors['ZoneEventsDetector'] = ZoneEventsDetector(objects_handler)
        self._detectors['ZoneEventsDetector'].set_params(**params.get('ZoneEventsDetector', {}))
        self._detectors['ZoneEventsDetector'].init()

        # AttributeEventsDetector
        self._detectors['AttributeEventsDetector'] = AttributeEventsDetector(objects_handler)
        self._detectors['AttributeEventsDetector'].set_params(**params.get('AttributeEventsDetector', {}))
        self._detectors['AttributeEventsDetector'].init()

        # SystemEventsDetector
        self._detectors['SystemEventsDetector'] = SystemEventsDetector()
        self._detectors['SystemEventsDetector'].set_params(**params.get('SystemEventsDetector', {}))
        self._detectors['SystemEventsDetector'].init()

        # Подписка объектов на детекторы
        objects_handler.subscribe(
            self._detectors['FieldOfViewEventsDetector'],
            self._detectors['ZoneEventsDetector'],
            self._detectors['AttributeEventsDetector'],
        )

        # Подписка источников на CamEventsDetector
        for source in sources:
            if hasattr(source, 'subscribe'):
                source.subscribe(self._detectors['CamEventsDetector'])

        self.logger.info(f"Initialized {len(self._detectors)} event detectors")

    def initialize_attribute_processors(
        self,
        pipeline: IPipeline,
        objects_handler: IObjectHandler,
        params: Dict[str, Any],
    ) -> None:
        """Инициализировать атрибутные процессоры и связать с ObjectsHandler.

        Args:
            pipeline: Pipeline для поиска процессоров
            objects_handler: ObjectsHandler для конфигурации
            params: Параметры конфигурации
        """
        if not hasattr(pipeline, 'processors'):
            return

        for processor in pipeline.processors:
            if hasattr(processor, 'get_name'):
                proc_name = processor.get_name()
                if proc_name in ['attributes_roi', 'attributes_classifier']:
                    attr_params = params.get('attributes_detection', {})
                    if attr_params:
                        # Прокидываем параметры в ObjectsHandler
                        if 'objects_handler' not in objects_handler.params:
                            objects_handler.params['objects_handler'] = {}
                        objects_handler.params['objects_handler']['attributes_detection'] = attr_params
                        if hasattr(objects_handler, 'set_params_impl'):
                            objects_handler.set_params_impl()
                        self.logger.info(f"Attribute detection configured for {proc_name}")

    def initialize_controller(self, params: Dict[str, Any]) -> None:
        """Инициализировать контроллер детекторов.

        Args:
            params: Параметры конфигурации контроллера
        """
        detectors_list = [
            self._detectors.get('CamEventsDetector'),
            self._detectors.get('FieldOfViewEventsDetector'),
            self._detectors.get('ZoneEventsDetector'),
        ]
        if self._detectors.get('AttributeEventsDetector'):
            detectors_list.append(self._detectors['AttributeEventsDetector'])
        if self._detectors.get('SystemEventsDetector'):
            detectors_list.append(self._detectors['SystemEventsDetector'])

        self._detectors_controller = EventsDetectorsController(detectors_list)
        self._detectors_controller.set_params(**params)
        self._detectors_controller.init()
        self.logger.info("Events detectors controller initialized")

    def initialize_processor(
        self,
        params: Dict[str, Any],
        adapters: List[Any],
        db_controller: Optional[Any] = None,
        ui_callback: Optional[callable] = None,
    ) -> None:
        """Инициализировать процессор событий.

        Args:
            params: Параметры конфигурации процессора
            adapters: Список адаптеров для сохранения событий
            db_controller: Контроллер БД (опционально)
            ui_callback: Callback для UI сигнализации (опционально)
        """
        self._events_processor = EventsProcessor(adapters, db_controller)
        self._events_processor.set_params(**params)
        self._events_processor.init()

        if ui_callback:
            try:
                self._events_processor.set_ui_callback(ui_callback)
            except Exception as e:
                self.logger.warning(f"Failed to set UI callback: {e}")

        self.logger.info("Events processor initialized")

    def get_detector(self, name: str) -> Optional[IEventDetector]:
        """Получить детектор по имени.

        Args:
            name: Имя детектора

        Returns:
            Детектор или None
        """
        return self._detectors.get(name)

    def get_all_detectors(self) -> Dict[str, IEventDetector]:
        """Получить все детекторы.

        Returns:
            Словарь {имя: детектор}
        """
        return self._detectors.copy()

    def get_detectors_controller(self) -> Optional[EventsDetectorsController]:
        """Получить контроллер детекторов.

        Returns:
            Контроллер детекторов или None
        """
        return self._detectors_controller

    def get_events_processor(self) -> Optional[EventsProcessor]:
        """Получить процессор событий.

        Returns:
            Процессор событий или None
        """
        return self._events_processor

    def start_detectors(self) -> None:
        """Запустить все детекторы."""
        for name, detector in self._detectors.items():
            try:
                detector.start()
                self.logger.debug(f"Started detector: {name}")
            except Exception as e:
                self.logger.error(f"Failed to start detector {name}: {e}")

    def stop_detectors(self) -> None:
        """Остановить все детекторы."""
        for name, detector in self._detectors.items():
            try:
                detector.stop()
                self.logger.debug(f"Stopped detector: {name}")
            except Exception as e:
                self.logger.error(f"Failed to stop detector {name}: {e}")

    def release(self) -> None:
        """Освободить ресурсы сервиса."""
        self.stop_detectors()
        self._detectors.clear()
        self._detectors_controller = None
        self._events_processor = None
        self.logger.info("Events service released")
