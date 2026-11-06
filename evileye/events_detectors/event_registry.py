"""Event detector factories backed by the shared plugin registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Type

from evileye.core.plugins import PluginError, plugin_manager, plugin_registry


DEFAULT_ENABLED_EVENT_DETECTORS = (
    "CamEventsDetector",
    "ScheduleAlarmEventsDetector",
    "ZoneEventsDetector",
    "AttributeEventsDetector",
    "SystemEventsDetector",
)


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
    execution_modes: tuple[str, ...] = ("thread",),
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
            execution_modes=execution_modes,
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


def _create_process_cam_detector(config):
    from evileye.events_detectors.process_cam_events_module import (
        create_process_cam_events_module,
    )

    return create_process_cam_events_module(config)


def _create_process_schedule_alarm_detector(config):
    from evileye.events_detectors.process_schedule_alarm_module import (
        create_process_schedule_alarm_module,
    )

    return create_process_schedule_alarm_module(config)


def _create_process_zone_detector(config):
    from evileye.events_detectors.process_zone_events_module import (
        create_process_zone_events_module,
    )

    return create_process_zone_events_module(config)


def _create_process_attribute_detector(config):
    from evileye.events_detectors.process_attribute_events_module import (
        create_process_attribute_events_module,
    )

    return create_process_attribute_events_module(config)


def _create_process_system_detector(config):
    from evileye.events_detectors.process_system_events_module import (
        create_process_system_events_module,
    )

    return create_process_system_events_module(config)


def register_builtins() -> None:
    """Idempotently register stock detector factories in the shared SPI."""
    plugin_manager.load()
    from evileye.events_detectors.schedule_alarm_logic import (
        DETECTOR_CONFIG_KEY,
        LEGACY_DETECTOR_CONFIG_KEY,
    )

    builtin_factories = {
        "CamEventsDetector": (
            _create_process_cam_detector, ("source_updates",), ("process",), "process",
        ),
        "ZoneEventsDetector": (
            _create_process_zone_detector,
            ("event_updates", "event_frames", "event_commands", "zone_commands"),
            ("process",),
            "process",
        ),
        "AttributeEventsDetector": (
            _create_process_attribute_detector,
            ("event_updates", "event_frames"),
            ("process",),
            "process",
        ),
        "SystemEventsDetector": (
            _create_process_system_detector, ("event_commands",), ("process",), "process",
        ),
        DETECTOR_CONFIG_KEY: (
            _create_process_schedule_alarm_detector, ("event_updates",), ("process",), "process",
        ),
        LEGACY_DETECTOR_CONFIG_KEY: (
            _create_process_schedule_alarm_detector, ("event_updates",), ("process",), "process",
        ),
    }
    for name, (factory, capabilities, execution_modes, default_mode) in builtin_factories.items():
        existing = plugin_registry.get_module(name)
        if existing is None:
            plugin_registry.register_builtin_module(
                name,
                factory,
                kind="event_detector",
                execution_modes=execution_modes,
                capabilities=capabilities,
                default_execution_mode=default_mode,
                legacy_ids=(name,),
            )
        elif (
            existing.spec.factory is not factory
            or tuple(existing.spec.execution_modes) != tuple(execution_modes)
            or tuple(existing.spec.capabilities) != tuple(capabilities)
        ):
            raise PluginError(
                f"Event detector id '{name}' is already registered by "
                f"'{existing.qualified_id}' with a different manifest"
            )
