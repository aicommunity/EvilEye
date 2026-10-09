"""Plugin registry for event detectors (DX / audit phase 3).

Built-in detectors register at import time. Custom detectors can use
``@register_event_detector("MyEvent")`` and enable via config:

```json
"events_detectors": {
  "enabled": ["ZoneEventsDetector", "MyEvent"],
  "MyEvent": { ... }
}
```

When ``enabled`` is omitted, all registered detectors that appear in the
built-in bootstrap set are started (backward compatible).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Type

from evileye.core.plugins import plugin_manager, plugin_registry

_EVENT_DETECTOR_REGISTRY: Dict[str, Type] = {}


def register_event_detector(name: str) -> Callable[[Type], Type]:
    """Decorator: register an event detector class under ``name``."""

    def _wrap(cls: Type) -> Type:
        name_value = str(name)
        existing = _EVENT_DETECTOR_REGISTRY.get(name_value)
        if existing is not None and existing is not cls:
            raise ValueError(f"Event detector id already registered: {name_value}")
        _EVENT_DETECTOR_REGISTRY[name_value] = cls
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
    plugin_manager.load()
    names = set(_EVENT_DETECTOR_REGISTRY)
    names.update(plugin_registry.list_modules("event_detector"))
    for module_id in plugin_registry.list_modules("event_detector"):
        registered = plugin_registry.get_module(module_id)
        if registered is not None:
            names.update(registered.spec.legacy_ids)
    return sorted(names)


def get_event_detector_class(name: str) -> Optional[Type]:
    registered = plugin_registry.get_module(str(name))
    if registered is not None and registered.spec.kind == "event_detector":
        return registered.spec.factory
    return _EVENT_DETECTOR_REGISTRY.get(str(name))


def create_event_detector(name: str, *args: Any, **kwargs: Any) -> Any:
    plugin_manager.load()
    cls = get_event_detector_class(name)
    if cls is None:
        raise KeyError(f"Event detector not registered: {name}")
    return cls(*args, **kwargs)


def register_builtins() -> None:
    """Idempotent registration of stock detectors."""
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
        existing = _EVENT_DETECTOR_REGISTRY.get(name)
        if existing is not None and existing is not detector_class:
            raise ValueError(f"Event detector id already registered: {name}")
        _EVENT_DETECTOR_REGISTRY[name] = detector_class
        # Register each builtin in the shared SPI while retaining its legacy key.
        if plugin_registry.get_module(f"evileye/{name}") is None:
            plugin_registry.register_builtin_module(
                name,
                detector_class,
                kind="event_detector",
                execution_modes=("thread",),
                legacy_ids=(name,),
            )
