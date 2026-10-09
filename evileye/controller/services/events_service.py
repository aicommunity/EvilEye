"""Сервис управления детекторами событий и их обработкой."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from evileye.core.interfaces import IEventDetector, IObjectHandler, IPipeline
from evileye.core.logger import get_module_logger
from evileye.database_controller.json_adapter_attribute_events import JsonAdapterAttributeEvents
from evileye.database_controller.json_adapter_alarm_events import JsonAdapterAlarmEvents
from evileye.database_controller.json_adapter_cam_events import JsonAdapterCamEvents
from evileye.database_controller.json_adapter_schedule_alarm_events import JsonAdapterScheduleAlarmEvents
from evileye.database_controller.json_adapter_system_events import JsonAdapterSystemEvents
from evileye.database_controller.json_adapter_zone_events import JsonAdapterZoneEvents
from evileye.events_control.events_controller import EventsDetectorsController
from evileye.events_control.events_processor import EventsProcessor
from evileye.events_detectors.event_registry import (
    create_event_detector,
    list_event_detectors,
    register_builtins,
)
from evileye.events_detectors.schedule_alarm_logic import (
    DETECTOR_CONFIG_KEY,
    LEGACY_DETECTOR_CONFIG_KEY,
    resolve_detector_section,
)
from evileye.core.plugins import plugin_registry

JSON_EVENT_ADAPTER_CLASSES = (
    JsonAdapterAlarmEvents,
    JsonAdapterAttributeEvents,
    JsonAdapterScheduleAlarmEvents,
    JsonAdapterZoneEvents,
    JsonAdapterCamEvents,
    JsonAdapterSystemEvents,
)

# Default bootstrap order when config omits events_detectors.enabled
_DEFAULT_ENABLED = (
    "CamEventsDetector",
    DETECTOR_CONFIG_KEY,
    "ZoneEventsDetector",
    "AttributeEventsDetector",
    "SystemEventsDetector",
)


class EventsService:
    """Сервис для управления детекторами событий и их обработкой."""

    def __init__(self):
        """Инициализация сервиса."""
        self.logger = get_module_logger("events_service")
        self._detectors: Dict[str, IEventDetector] = {}
        self._detectors_controller: Optional[EventsDetectorsController] = None
        self._events_processor: Optional[EventsProcessor] = None
        self._adapters: List[Any] = []

    def initialize_detectors(
            self,
            params: Dict[str, Any],
            pipeline: IPipeline,
            objects_handler: IObjectHandler,
            use_database: bool = True,
    ) -> None:
        """Инициализировать детекторы событий через plugin registry."""
        register_builtins()
        sources = pipeline.get_sources()
        pipeline_source_ids = list(range(len(sources)))

        enabled = params.get("enabled")
        if enabled is None:
            enabled_list = list(_DEFAULT_ENABLED)
        elif isinstance(enabled, list):
            enabled_list = [str(x) for x in enabled]
        else:
            enabled_list = list(_DEFAULT_ENABLED)

        self.logger.info(
            "Event detectors enabled=%s (registered=%s)",
            enabled_list,
            list_event_detectors(),
        )

        for name in enabled_list:
            if name in self._detectors:
                continue
            try:
                detector = self._instantiate_detector(
                    name,
                    sources=sources,
                    objects_handler=objects_handler,
                    pipeline_source_ids=pipeline_source_ids,
                    params=params,
                )
            except KeyError:
                raise ValueError(f"Unknown event detector '{name}'")
            except Exception as exc:
                self.logger.error("Failed to create event detector %s: %s", name, exc, exc_info=True)
                raise RuntimeError(f"Failed to create event detector '{name}'") from exc
            section = params.get(name, {}) if name not in {DETECTOR_CONFIG_KEY, LEGACY_DETECTOR_CONFIG_KEY} else resolve_detector_section(params)
            if name in {DETECTOR_CONFIG_KEY, LEGACY_DETECTOR_CONFIG_KEY}:
                section = resolve_detector_section(params)
            detector_config = section or {}
            registered = plugin_registry.get_module(name)
            if registered is not None and registered.spec.config_schema is not None:
                detector_config = plugin_registry.validate_module_config(name, detector_config)
            detector.set_params(**detector_config)
            detector.init()
            self._detectors[name] = detector
            if name == DETECTOR_CONFIG_KEY:
                self._detectors[LEGACY_DETECTOR_CONFIG_KEY] = detector
            elif name == LEGACY_DETECTOR_CONFIG_KEY:
                self._detectors[DETECTOR_CONFIG_KEY] = detector

        # Cam sources subscribe to cam detector when present
        cam = self._detectors.get("CamEventsDetector")
        if cam is not None:
            try:
                for source in sources:
                    if hasattr(source, "subscribe"):
                        source.subscribe(cam)
            except Exception:
                pass

        # ObjectsHandler subscribers (schedule/zone/attr) when present
        oh_subs = [
            self._detectors.get(DETECTOR_CONFIG_KEY),
            self._detectors.get("ZoneEventsDetector"),
            self._detectors.get("AttributeEventsDetector"),
        ]
        for name in enabled_list:
            registered = plugin_registry.get_module(name)
            detector = self._detectors.get(name)
            if (
                registered is not None
                and registered.spec.kind == "event_detector"
                and "object_handler" in registered.spec.capabilities
                and detector is not None
            ):
                oh_subs.append(detector)
        unique_subscribers = []
        seen_subscribers: set[int] = set()
        for detector in oh_subs:
            if detector is not None and id(detector) not in seen_subscribers:
                unique_subscribers.append(detector)
                seen_subscribers.add(id(detector))
        oh_subs = unique_subscribers
        if oh_subs:
            try:
                objects_handler.subscribe(*oh_subs)
            except Exception as exc:
                self.logger.warning("objects_handler.subscribe failed: %s", exc)

        self.logger.info(
            "Initialized %s event detectors (use_database=%s)",
            len(self._detectors),
            use_database,
        )

    def _instantiate_detector(
        self,
        name: str,
        *,
        sources,
        objects_handler,
        pipeline_source_ids,
        params: Dict[str, Any],
    ):
        if name == "CamEventsDetector":
            return create_event_detector(name, sources)
        if name in {DETECTOR_CONFIG_KEY, LEGACY_DETECTOR_CONFIG_KEY}:
            return create_event_detector(
                DETECTOR_CONFIG_KEY,
                objects_handler,
                pipeline_source_ids=pipeline_source_ids,
            )
        if name in {"ZoneEventsDetector", "AttributeEventsDetector"}:
            return create_event_detector(name, objects_handler)
        if name == "SystemEventsDetector":
            return create_event_detector(name)
        # Custom detectors: try (objects_handler) then no-arg
        try:
            return create_event_detector(name, objects_handler)
        except TypeError:
            return create_event_detector(name)

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
        # Preserve order; skip missing; dedupe aliases (ScheduleAlarm / FOV).
        preferred = [
            "CamEventsDetector",
            DETECTOR_CONFIG_KEY,
            "ZoneEventsDetector",
            "AttributeEventsDetector",
            "SystemEventsDetector",
        ]
        seen: set[int] = set()
        detectors_list = []
        for name in preferred:
            det = self._detectors.get(name)
            if det is None or id(det) in seen:
                continue
            seen.add(id(det))
            detectors_list.append(det)
        for name, det in self._detectors.items():
            if id(det) in seen:
                continue
            seen.add(id(det))
            detectors_list.append(det)

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
        alarm_db_adapter = None

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
                from evileye.database_controller.db_adapter_alarm_events import DatabaseAdapterAlarmEvents

                alarm_db_adapter = DatabaseAdapterAlarmEvents(db_controller)
                alarm_db_adapter.set_params(table_name="alarm_events")
                alarm_db_adapter.init()
                alarm_db_adapter.start()
                adapters.append(alarm_db_adapter)
            except Exception as exc:
                self.logger.error("Failed to initialize alarm database adapter: %s", exc)
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

        from evileye.utils.database_config_utils import resolve_writable_image_dir

        preferred = (params.get("database", {}) or {}).get("image_dir") or "EvilEyeData"
        img_dir = resolve_writable_image_dir(preferred)
        db_section = params.get("database")
        if not isinstance(db_section, dict):
            db_section = {}
            params["database"] = db_section
        db_section["image_dir"] = img_dir

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
                if adapter_cls is JsonAdapterAlarmEvents:
                    if alarm_db_adapter is not None:
                        try:
                            alarm_db_adapter.stop()
                        except Exception:
                            pass
                    raise RuntimeError("Generic alarm persistence is unavailable") from e

        return adapters

    def apply_legacy_detector_refs(self, host: Any) -> None:
        """Синхронизировать legacy-атрибуты Controller с детекторами сервиса."""
        host.cam_events_detector = self.get_detector("CamEventsDetector")
        host.schedule_alarm_events_detector = self.get_detector(DETECTOR_CONFIG_KEY)
        host.fov_events_detector = host.schedule_alarm_events_detector
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
        self._adapters = list(adapters)
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
        seen: set[int] = set()
        for name, detector in self._detectors.items():
            det_id = id(detector)
            if det_id in seen:
                continue
            seen.add(det_id)
            try:
                detector.start()
                self.logger.debug(f"Started detector: {name}")
            except Exception as e:
                self.logger.error(f"Failed to start detector {name}: {e}")

    def stop_detectors(self) -> None:
        seen: set[int] = set()
        for name, detector in self._detectors.items():
            det_id = id(detector)
            if det_id in seen:
                continue
            seen.add(det_id)
            try:
                detector.stop()
                self.logger.debug(f"Stopped detector: {name}")
            except Exception as e:
                self.logger.error(f"Failed to stop detector {name}: {e}")

    def release(self) -> None:
        self.stop_detectors()
        if self._events_processor is not None:
            try:
                self._events_processor.stop()
            except Exception:
                pass
        seen: set[int] = set()
        for adapter in self._adapters:
            if adapter is None or id(adapter) in seen:
                continue
            seen.add(id(adapter))
            try:
                adapter.stop()
            except Exception:
                pass
        self._detectors.clear()
        self._detectors_controller = None
        self._events_processor = None
        self._adapters.clear()
        self.logger.info("Events service released")
