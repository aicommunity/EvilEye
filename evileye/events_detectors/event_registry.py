"""Event detector factories backed by the shared plugin registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Type

from evileye.core.plugins import PluginError, plugin_manager, plugin_registry


@dataclass(frozen=True)
class EventDetectorContext:
    """Dependencies supplied to every event detector factory."""

    sources: tuple[Any, ...] = ()
    objects_handler: Any | None = None
    pipeline_source_ids: tuple[int, ...] = ()


def register_event_detector(
    name: str,
    *,
    capabilities: tuple[str, ...] = (),
) -> Callable[[Type], Type]:
    """Register a factory whose constructor accepts ``EventDetectorContext``."""

    def _wrap(factory: Type) -> Type:
        name_value = str(name).strip()
        if not name_value:
            raise ValueError("Event detector id must not be empty")
        plugin_registry.register_builtin_module(
            name_value,
            factory,
            kind="event_detector",
            execution_modes=("thread",),
            capabilities=capabilities,
            legacy_ids=(name_value,),
        )
        return factory

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
    """Return the registered event detector factory for a module id."""
    registered = plugin_registry.get_module(str(name))
    if registered is not None and registered.spec.kind == "event_detector":
        return registered.spec.factory
    return None


def create_event_detector(name: str, context: EventDetectorContext) -> Any:
    """Instantiate a registered event detector with its shared dependency context."""
    plugin_manager.load()
    registered = plugin_registry.get_module(str(name))
    if registered is None or registered.spec.kind != "event_detector":
        raise KeyError(f"Event detector not registered in plugin registry: {name}")
    if not isinstance(context, EventDetectorContext):
        raise PluginError("Event detector factories require EventDetectorContext")
    from evileye.core.base_class import EvilEyeBase

    return EvilEyeBase.create_instance(registered.qualified_id, context)


def _create_cam_detector(context: EventDetectorContext):
    from evileye.events_detectors.cam_events_detector import CamEventsDetector

    return CamEventsDetector(list(context.sources))


def _create_zone_detector(context: EventDetectorContext):
    from evileye.events_detectors.zone_events_detector import ZoneEventsDetector

    if context.objects_handler is None:
        raise PluginError("ZoneEventsDetector requires objects_handler")
    return ZoneEventsDetector(context.objects_handler)


def _create_attribute_detector(context: EventDetectorContext):
    from evileye.events_detectors.attribute_events_detector import AttributeEventsDetector

    if context.objects_handler is None:
        raise PluginError("AttributeEventsDetector requires objects_handler")
    return AttributeEventsDetector(context.objects_handler)


def _create_schedule_alarm_detector(context: EventDetectorContext):
    from evileye.events_detectors.schedule_alarm_events_detector import ScheduleAlarmEventsDetector

    if context.objects_handler is None:
        raise PluginError("ScheduleAlarmEventsDetector requires objects_handler")
    return ScheduleAlarmEventsDetector(
        context.objects_handler,
        pipeline_source_ids=list(context.pipeline_source_ids),
    )


def _create_system_detector(context: EventDetectorContext):
    from evileye.events_detectors.system_events_detector import SystemEventsDetector

    return SystemEventsDetector()


def register_builtins() -> None:
    """Idempotently register stock detector factories in the shared SPI."""
    plugin_manager.load()
    from evileye.events_detectors.schedule_alarm_logic import (
        DETECTOR_CONFIG_KEY,
        LEGACY_DETECTOR_CONFIG_KEY,
    )

    builtin_factories = {
        "CamEventsDetector": (_create_cam_detector, ("capture_sources",)),
        "ZoneEventsDetector": (_create_zone_detector, ("object_handler",)),
        "AttributeEventsDetector": (_create_attribute_detector, ("object_handler",)),
        "SystemEventsDetector": (_create_system_detector, ()),
        DETECTOR_CONFIG_KEY: (_create_schedule_alarm_detector, ("object_handler",)),
        LEGACY_DETECTOR_CONFIG_KEY: (_create_schedule_alarm_detector, ("object_handler",)),
    }
    for name, (factory, capabilities) in builtin_factories.items():
        existing = plugin_registry.get_module(name)
        if existing is None:
            plugin_registry.register_builtin_module(
                name,
                factory,
                kind="event_detector",
                execution_modes=("thread",),
                capabilities=capabilities,
                legacy_ids=(name,),
            )
        elif existing.spec.factory is not factory:
            raise PluginError(
                f"Event detector id '{name}' is already registered by "
                f"'{existing.qualified_id}'"
            )
