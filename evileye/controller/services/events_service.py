"""Сервис управления детекторами событий и их обработкой."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from evileye.core.interfaces import IEventDetector, IObjectHandler, IPipeline
from evileye.core.logger import get_module_logger
from evileye.database_controller.json_adapter_attribute_events import JsonAdapterAttributeEvents
from evileye.database_controller.json_adapter_cam_events import JsonAdapterCamEvents
from evileye.database_controller.json_adapter_fov_events import JsonAdapterFovEvents
from evileye.database_controller.json_adapter_system_events import JsonAdapterSystemEvents
from evileye.database_controller.json_adapter_zone_events import JsonAdapterZoneEvents
from evileye.events_control.events_controller import EventsDetectorsController
from evileye.events_control.events_processor import EventsProcessor
from evileye.events_detectors.attribute_events_detector import AttributeEventsDetector
from evileye.events_detectors.cam_events_detector import CamEventsDetector
from evileye.events_detectors.fov_events_detector import FieldOfViewEventsDetector
from evileye.events_detectors.system_events_detector import SystemEventsDetector
from evileye.events_detectors.zone_events_detector import ZoneEventsDetector

JSON_EVENT_ADAPTER_CLASSES = (
    JsonAdapterAttributeEvents,
    JsonAdapterFovEvents,
    JsonAdapterZoneEvents,
    JsonAdapterCamEvents,
    JsonAdapterSystemEvents,
)


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
        """Инициализировать детекторы событий."""
        sources = pipeline.get_sources()
        self._detectors["CamEventsDetector"] = CamEventsDetector(sources)
        self._detectors["CamEventsDetector"].set_params(**params.get("CamEventsDetector", {}))
        self._detectors["CamEventsDetector"].init()

        self._detectors["FieldOfViewEventsDetector"] = FieldOfViewEventsDetector(objects_handler)
        self._detectors["FieldOfViewEventsDetector"].set_params(
            **params.get("FieldOfViewEventsDetector", {})
        )
        self._detectors["FieldOfViewEventsDetector"].init()

        self._detectors["ZoneEventsDetector"] = ZoneEventsDetector(objects_handler)
        self._detectors["ZoneEventsDetector"].set_params(**params.get("ZoneEventsDetector", {}))
        self._detectors["ZoneEventsDetector"].init()

        self._detectors["AttributeEventsDetector"] = AttributeEventsDetector(objects_handler)
        self._detectors["AttributeEventsDetector"].set_params(
            **params.get("AttributeEventsDetector", {})
        )
        self._detectors["AttributeEventsDetector"].init()

        self._detectors["SystemEventsDetector"] = SystemEventsDetector()
        self._detectors["SystemEventsDetector"].set_params(**params.get("SystemEventsDetector", {}))
        self._detectors["SystemEventsDetector"].init()

        objects_handler.subscribe(
            self._detectors["FieldOfViewEventsDetector"],
            self._detectors["ZoneEventsDetector"],
            self._detectors["AttributeEventsDetector"],
        )

        for source in sources:
            if hasattr(source, "subscribe"):
                source.subscribe(self._detectors["CamEventsDetector"])

        self.logger.info(
            "Initialized %s event detectors (use_database=%s)",
            len(self._detectors),
            use_database,
        )

    def initialize_attribute_processors(
        self,
        pipeline: IPipeline,
        objects_handler: IObjectHandler,
        params: Dict[str, Any],
    ) -> None:
        """Инициализировать атрибутные процессоры и связать с ObjectsHandler."""
        if not hasattr(pipeline, "processors"):
            return

        for processor in pipeline.processors:
            if hasattr(processor, "get_name"):
                proc_name = processor.get_name()
                if proc_name in ["attributes_roi", "attributes_classifier"]:
                    attr_params = params.get("attributes_detection", {})
                    if attr_params:
                        if "objects_handler" not in objects_handler.params:
                            objects_handler.params["objects_handler"] = {}
                        objects_handler.params["objects_handler"]["attributes_detection"] = attr_params
                        if hasattr(objects_handler, "set_params_impl"):
                            objects_handler.set_params_impl()
                        self.logger.info(f"Attribute detection configured for {proc_name}")

    def initialize_controller(self, params: Dict[str, Any]) -> None:
        """Инициализировать контроллер детекторов."""
        detectors_list = [
            self._detectors.get("CamEventsDetector"),
            self._detectors.get("FieldOfViewEventsDetector"),
            self._detectors.get("ZoneEventsDetector"),
        ]
        if self._detectors.get("AttributeEventsDetector"):
            detectors_list.append(self._detectors["AttributeEventsDetector"])
        if self._detectors.get("SystemEventsDetector"):
            detectors_list.append(self._detectors["SystemEventsDetector"])

        self._detectors_controller = EventsDetectorsController(detectors_list)
        self._detectors_controller.set_params(**params)
        self._detectors_controller.init()
        self.logger.info("Events detectors controller initialized")

    def build_event_adapters(
        self,
        *,
        params: Dict[str, Any],
        use_database: bool,
        db_controller: Optional[Any],
        db_adapter_fov_events: Optional[Any] = None,
        db_adapter_cam_events: Optional[Any] = None,
        db_adapter_zone_events: Optional[Any] = None,
        db_adapter_attr_events: Optional[Any] = None,
        db_adapter_system_events: Optional[Any] = None,
    ) -> List[Any]:
        """Собрать DB и JSON адаптеры для EventsProcessor."""
        adapters: List[Any] = []

        if use_database and db_controller and db_controller.is_connected():
            adapters.extend(
                [
                    db_adapter_fov_events,
                    db_adapter_cam_events,
                    db_adapter_zone_events,
                ]
            )
            if db_adapter_attr_events:
                adapters.append(db_adapter_attr_events)
            if db_adapter_system_events:
                adapters.append(db_adapter_system_events)
            try:
                self.logger.info(
                    "DB adapters: %s",
                    [a.get_event_name() for a in adapters if a],
                )
            except Exception:
                pass
        elif use_database and db_controller:
            self.logger.info(
                "Database was enabled but connection failed. Using JSON-only mode for events."
            )

        img_dir = (params.get("database", {}) or {}).get("image_dir", "EvilEyeData")
        for adapter_cls in JSON_EVENT_ADAPTER_CLASSES:
            try:
                adapter = adapter_cls(None)
                adapter.set_params(image_dir=img_dir)
                adapter.init()
                adapter.start()
                adapters.append(adapter)
                try:
                    self.logger.info(
                        "JSON adapter started: %s -> image_dir=%s",
                        adapter.get_event_name(),
                        img_dir,
                    )
                except Exception:
                    pass
            except Exception as e:
                try:
                    self.logger.error("Failed to start JSON adapter %s: %s", adapter_cls.__name__, e)
                except Exception:
                    pass

        return adapters

    def apply_legacy_detector_refs(self, host: Any) -> None:
        """Синхронизировать legacy-атрибуты Controller с детекторами сервиса."""
        host.cam_events_detector = self.get_detector("CamEventsDetector")
        host.fov_events_detector = self.get_detector("FieldOfViewEventsDetector")
        host.zone_events_detector = self.get_detector("ZoneEventsDetector")
        host.attr_events_detector = self.get_detector("AttributeEventsDetector")
        host.system_events_detector = self.get_detector("SystemEventsDetector")

    def initialize_events_stack(
        self,
        *,
        pipeline: IPipeline,
        objects_handler: IObjectHandler,
        params: Dict[str, Any],
        use_database: bool,
        db_controller: Optional[Any],
        legacy_host: Any,
        ui_callback: Optional[callable] = None,
        db_adapter_fov_events: Optional[Any] = None,
        db_adapter_cam_events: Optional[Any] = None,
        db_adapter_zone_events: Optional[Any] = None,
        db_adapter_attr_events: Optional[Any] = None,
        db_adapter_system_events: Optional[Any] = None,
    ) -> None:
        """Полная инициализация детекторов, контроллера и процессора событий."""
        detectors_params = params.get("events_detectors", {}) or {}
        processor_params = params.get("events_processor", {}) or {}

        self.initialize_detectors(
            params=detectors_params,
            pipeline=pipeline,
            objects_handler=objects_handler,
            use_database=use_database,
        )
        self.apply_legacy_detector_refs(legacy_host)
        self.initialize_attribute_processors(
            pipeline=pipeline,
            objects_handler=objects_handler,
            params=params,
        )
        self.initialize_controller(detectors_params)
        legacy_host.events_detectors_controller = self.get_detectors_controller()

        adapters = self.build_event_adapters(
            params=params,
            use_database=use_database,
            db_controller=db_controller,
            db_adapter_fov_events=db_adapter_fov_events,
            db_adapter_cam_events=db_adapter_cam_events,
            db_adapter_zone_events=db_adapter_zone_events,
            db_adapter_attr_events=db_adapter_attr_events,
            db_adapter_system_events=db_adapter_system_events,
        )
        self.initialize_processor(
            params=processor_params,
            adapters=adapters,
            db_controller=db_controller if use_database else None,
            ui_callback=ui_callback,
        )
        legacy_host.events_processor = self.get_events_processor()

    def initialize_processor(
        self,
        params: Dict[str, Any],
        adapters: List[Any],
        db_controller: Optional[Any] = None,
        ui_callback: Optional[callable] = None,
    ) -> None:
        """Инициализировать процессор событий."""
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
        return self._detectors.get(name)

    def get_all_detectors(self) -> Dict[str, IEventDetector]:
        return self._detectors.copy()

    def get_detectors_controller(self) -> Optional[EventsDetectorsController]:
        return self._detectors_controller

    def get_events_processor(self) -> Optional[EventsProcessor]:
        return self._events_processor

    def start_detectors(self) -> None:
        for name, detector in self._detectors.items():
            try:
                detector.start()
                self.logger.debug(f"Started detector: {name}")
            except Exception as e:
                self.logger.error(f"Failed to start detector {name}: {e}")

    def stop_detectors(self) -> None:
        for name, detector in self._detectors.items():
            try:
                detector.stop()
                self.logger.debug(f"Stopped detector: {name}")
            except Exception as e:
                self.logger.error(f"Failed to stop detector {name}: {e}")

    def release(self) -> None:
        self.stop_detectors()
        self._detectors.clear()
        self._detectors_controller = None
        self._events_processor = None
        self.logger.info("Events service released")
