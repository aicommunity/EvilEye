from __future__ import annotations

from typing import Any

from evileye.visualization_modules.journal_adapters.jadapter_cam_events import JournalAdapterCamEvents
from evileye.visualization_modules.journal_adapters.jadapter_fov_events import JournalAdapterFieldOfViewEvents
from evileye.visualization_modules.journal_adapters.jadapter_zone_events import JournalAdapterZoneEvents


def _adapter_params(runtime_params: dict[str, Any]) -> dict[str, Any]:
    database = runtime_params.get("database") if isinstance(runtime_params, dict) else None
    if isinstance(database, dict):
        params = database.get("adapters")
        if isinstance(params, dict):
            return params
    return {}


def create_event_journal_adapters(db_controller, runtime_params: dict[str, Any]) -> list:
    """Initialize journal adapters for events SQL (mirrors db_journal._init_adapters)."""
    adapter_params = _adapter_params(runtime_params)
    adapters = []

    cam = JournalAdapterCamEvents()
    cam.set_params(**adapter_params.get("DatabaseAdapterCamEvents", {}))
    cam.init()
    adapters.append(cam)

    fov = JournalAdapterFieldOfViewEvents()
    fov.set_params(**adapter_params.get("DatabaseAdapterFieldOfViewEvents", {}))
    fov.init()
    adapters.append(fov)

    zone = JournalAdapterZoneEvents()
    zone.set_params(**adapter_params.get("DatabaseAdapterZoneEvents", {}))
    zone.init()
    adapters.append(zone)

    try:
        from evileye.visualization_modules.journal_adapters.jadapter_attribute_events import JournalAdapterAttributeEvents

        attr = JournalAdapterAttributeEvents()
        if "DatabaseAdapterAttributeEvents" in adapter_params:
            attr.set_params(**adapter_params["DatabaseAdapterAttributeEvents"])
        else:
            attr.set_params(**{"table_name": "attribute_events"})
        attr.init()
        adapters.append(attr)
    except Exception:
        pass

    try:
        from evileye.visualization_modules.journal_adapters.jadapter_system_events import JournalAdapterSystemEvents

        system = JournalAdapterSystemEvents()
        if "DatabaseAdapterSystemEvents" in adapter_params:
            system.set_params(**adapter_params["DatabaseAdapterSystemEvents"])
        else:
            system.set_params(**{"table_name": "system_events"})
        system.init()
        adapters.append(system)
    except Exception:
        pass

    return adapters
