from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from evileye.api.core.server_state import iter_log_files, list_run_summaries
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
    runs = list_run_summaries()
    for run in runs:
        config_path = run.get("config_path")
        if not config_path:
            continue
        try:
            payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


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
    source = DatabaseJournalDataSource(
        controller,
        journal_type="events",
        database_params={"database": _database_config()},
        params=_runtime_params(),
    )
    items = source.fetch(page, size, filters, sort=[("ts", "desc")])
    total = source.get_total(filters)
    return {"available": True, "items": items, "total": total}


def load_objects_page(*, page: int, size: int, filters: Dict[str, Any]) -> dict[str, Any]:
    controller = _db_controller()
    if controller is None:
        return {"available": False, "items": [], "total": 0}
    source = DatabaseJournalDataSource(
        controller,
        journal_type="objects",
        database_params={"database": _database_config()},
        params=_runtime_params(),
    )
    items = source.fetch(page, size, filters, sort=[("ts", "desc")])
    total = source.get_total(filters)
    return {"available": True, "items": items, "total": total}


def load_config_history(*, limit: int) -> dict[str, Any]:
    controller = _db_controller()
    if controller is None:
        return {"available": False, "items": []}
    manager = ConfigHistoryManager(controller)
    items = manager.get_config_history(limit=limit)
    return {"available": True, "items": items}


def load_system_logs(*, lines: int) -> dict[str, Any]:
    files = []
    for path in iter_log_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        files.append(
            {
                "name": path.name,
                "updated_at": path.stat().st_mtime,
                "lines": text[-lines:],
            }
        )
    return {"available": bool(files), "files": files}
