"""Event detector registration backed by the shared plugin registry.

Built-in and installed detectors use the same ``ModuleSpec`` registry. The
legacy event-detector names remain aliases for existing configurations.
"""

from __future__ import annotations

from typing import Any, Callable, List, Type

from evileye.core.plugins import plugin_manager, plugin_registry


def register_event_detector(name: str) -> Callable[[Type], Type]:
    """Register an event detector factory in the shared plugin SPI."""

    def _wrap(cls: Type) -> Type:
        name_value = str(name).strip()
        if not name_value:
            raise ValueError("Event detector id must not be empty")
        plugin_registry.register_builtin_module(
            name_value,
            cls,
            kind="event_detector",
            execution_modes=("thread",),
            legacy_ids=(name_value,),
        )
        return cls

    return _wrap


def list_event_detectors() -> List[str]:
    """Return qualified module ids and their configured legacy aliases."""
    plugin_manager.load()
    names = set(plugin_registry.list_modules("event_detector"))
    for module_id in plugin_registry.list_modules("event_detector"):
        registered = plugin_registry.get_module(module_id)
        if registered is not None:
            names.update(registered.spec.legacy_ids)
    return sorted(names)


def get_event_detector_class(name: str) -> Type | None:
    registered = plugin_registry.get_module(str(name))
    if registered is not None and registered.spec.kind == "event_detector":
        return registered.spec.factory
    return None


def create_event_detector(name: str, *args: Any, **kwargs: Any) -> Any:
    plugin_manager.load()
    detector_class = get_event_detector_class(name)
    if detector_class is None:
        raise KeyError(f"Event detector not registered in plugin registry: {name}")
    return detector_class(*args, **kwargs)


def register_builtins() -> None:
    """Idempotently register stock detectors in the shared SPI."""
    plugin_manager.load()
    from evileye.events_detectors.attribute_events_detector import AttributeEventsDetector
    from evileye.events_detectors.cam_events_detector import CamEventsDetector
    from evileye.events_detectors.schedule_alarm_events_detector import ScheduleAlarmEventsDetector
    from evileye.events_detectors.system_events_detector import SystemEventsDetector
    from evileye.events_detectors.zone_events_detector import ZoneEventsDetector
    from evileye.events_detectors.schedule_alarm_logic import (
        DETECTOR_CONFIG_KEY,
        LEGACY_DETECTOR_CONFIG_KEY,
    )

    builtin_detectors = {
        "CamEventsDetector": CamEventsDetector,
        "ZoneEventsDetector": ZoneEventsDetector,
        "AttributeEventsDetector": AttributeEventsDetector,
        "SystemEventsDetector": SystemEventsDetector,
        DETECTOR_CONFIG_KEY: ScheduleAlarmEventsDetector,
        LEGACY_DETECTOR_CONFIG_KEY: ScheduleAlarmEventsDetector,
    }
    for name, detector_class in builtin_detectors.items():
        existing = plugin_registry.get_module(name)
        if existing is None:
            plugin_registry.register_builtin_module(
                name,
                detector_class,
                kind="event_detector",
                execution_modes=("thread",),
                legacy_ids=(name,),
            )
        elif existing.spec.factory is not detector_class:
            raise ValueError(
                f"Event detector id '{name}' is already registered by "
                f"'{existing.qualified_id}'"
            )
