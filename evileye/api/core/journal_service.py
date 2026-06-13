from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from evileye.api.core.server_state import get_current_run_summary
from evileye.database.config_history_manager import ConfigHistoryManager
from evileye.database_controller.database_controller_pg import DatabaseControllerPg
from evileye.visualization_modules.journal_data_source_db import DatabaseJournalDataSource


def _load_credentials() -> dict[str, Any]:
    path = Path("credentials.json")
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _database_config() -> dict[str, Any]:
    credentials = _load_credentials()
    database = credentials.get("database") if isinstance(credentials, dict) else {}
    return database if isinstance(database, dict) else {}


def _runtime_params() -> dict[str, Any]:
    current_run = get_current_run_summary()
    if not current_run:
        return {}
    snapshot = current_run.get("runtime_snapshot") if isinstance(current_run, dict) else None
    if isinstance(snapshot, dict):
        payload = snapshot.get("config")
        if isinstance(payload, dict):
            return payload
    config_path = current_run.get("config_path")
    if config_path:
        try:
            payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
        except Exception:
            payload = None
        if isinstance(payload, dict):
            return payload
    return {}


def _current_source_names() -> set[str]:
    params = _runtime_params()
    source_names: set[str] = set()
    pipeline = params.get("pipeline") if isinstance(params, dict) else None
    if not isinstance(pipeline, dict):
        pipeline = params
    sources = pipeline.get("sources") if isinstance(pipeline, dict) else None
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        for name in source.get("source_names") or []:
            if name:
                source_names.add(str(name))
    return source_names


def _merge_current_filters(filters: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(filters)
    source_names = _current_source_names()
    if source_names and "source_name" not in merged:
        merged["source_names"] = sorted(source_names)
    return merged


def _db_controller() -> Optional[DatabaseControllerPg]:
    db_config = _database_config()
    if not db_config:
        return None
    controller = DatabaseControllerPg(_runtime_params())
    try:
        controller.set_params(**db_config)
        controller.init()
        controller.connect()
        if not controller.is_connected():
            return None
        return controller
    except Exception:
        return None


def load_events_page(*, page: int, size: int, filters: Dict[str, Any]) -> dict[str, Any]:
    controller = _db_controller()
    if controller is None:
        return {"available": False, "items": [], "total": 0}
    scoped_filters = _merge_current_filters(filters)
    source = DatabaseJournalDataSource(
        controller,
        journal_type="events",
        database_params={"database": _database_config()},
        params=_runtime_params(),
    )
    items = source.fetch(page, size, scoped_filters, sort=[("ts", "desc")])
    total = source.get_total(scoped_filters)
    return {"available": True, "items": items, "total": total}


def load_objects_page(*, page: int, size: int, filters: Dict[str, Any]) -> dict[str, Any]:
    controller = _db_controller()
    if controller is None:
        return {"available": False, "items": [], "total": 0}
    scoped_filters = _merge_current_filters(filters)
    source = DatabaseJournalDataSource(
        controller,
        journal_type="objects",
        database_params={"database": _database_config()},
        params=_runtime_params(),
    )
    items = source.fetch(page, size, scoped_filters, sort=[("ts", "desc")])
    total = source.get_total(scoped_filters)
    return {"available": True, "items": items, "total": total}


def load_config_history(*, limit: int) -> dict[str, Any]:
    controller = _db_controller()
    if controller is None:
        return {"available": False, "items": []}
    manager = ConfigHistoryManager(controller)
    items = manager.get_config_history(limit=limit)
    current_run = get_current_run_summary()
    config_path = current_run.get("config_path") if current_run else None
    if config_path:
        items = [
            item for item in items
            if config_path in json.dumps(item.get("configuration_info") or {}, ensure_ascii=False)
        ]
    return {"available": True, "items": items}
