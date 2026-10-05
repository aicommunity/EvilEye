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

_EVENT_DETECTOR_REGISTRY: Dict[str, Type] = {}


def register_event_detector(name: str) -> Callable[[Type], Type]:
    """Decorator: register an event detector class under ``name``."""

    def _wrap(cls: Type) -> Type:
        _EVENT_DETECTOR_REGISTRY[str(name)] = cls
        return cls

    return _wrap


def list_event_detectors() -> List[str]:
    return sorted(_EVENT_DETECTOR_REGISTRY.keys())


def get_event_detector_class(name: str) -> Optional[Type]:
    return _EVENT_DETECTOR_REGISTRY.get(str(name))


def create_event_detector(name: str, *args: Any, **kwargs: Any) -> Any:
    cls = get_event_detector_class(name)
    if cls is None:
        raise KeyError(f"Event detector not registered: {name}")
    return cls(*args, **kwargs)


def register_builtins() -> None:
    """Idempotent registration of stock detectors."""
    if _EVENT_DETECTOR_REGISTRY:
        return
    from evileye.events_detectors.attribute_events_detector import AttributeEventsDetector
    from evileye.events_detectors.cam_events_detector import CamEventsDetector
    from evileye.events_detectors.schedule_alarm_events_detector import ScheduleAlarmEventsDetector
    from evileye.events_detectors.system_events_detector import SystemEventsDetector
    from evileye.events_detectors.zone_events_detector import ZoneEventsDetector
    from evileye.events_detectors.schedule_alarm_logic import (
        DETECTOR_CONFIG_KEY,
        LEGACY_DETECTOR_CONFIG_KEY,
    )

    _EVENT_DETECTOR_REGISTRY["CamEventsDetector"] = CamEventsDetector
    _EVENT_DETECTOR_REGISTRY["ZoneEventsDetector"] = ZoneEventsDetector
    _EVENT_DETECTOR_REGISTRY["AttributeEventsDetector"] = AttributeEventsDetector
    _EVENT_DETECTOR_REGISTRY["SystemEventsDetector"] = SystemEventsDetector
    _EVENT_DETECTOR_REGISTRY[DETECTOR_CONFIG_KEY] = ScheduleAlarmEventsDetector
    _EVENT_DETECTOR_REGISTRY[LEGACY_DETECTOR_CONFIG_KEY] = ScheduleAlarmEventsDetector
