from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from evileye.api.core.journal_adapters_factory import create_event_journal_adapters
from evileye.api.core.journal_grouping import group_events_rows, group_objects_rows
from evileye.api.core.server_state import get_current_run_summary
from evileye.database.config_history_manager import ConfigHistoryManager
from evileye.database_controller.database_controller_pg import DatabaseControllerPg
from evileye.visualization_modules.journal_data_source_db import DatabaseJournalDataSource
from evileye.visualization_modules.journal_data_source_json import JsonLabelJournalDataSource


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


def _database_enabled_in_config() -> bool:
    params = _runtime_params()
    controller = params.get("controller") if isinstance(params, dict) else None
    if isinstance(controller, dict) and "use_database" in controller:
        return bool(controller.get("use_database"))
    return True


def _image_base_dir() -> str:
    params = _runtime_params()
    controller = params.get("controller") if isinstance(params, dict) else None
    if isinstance(controller, dict):
        image_dir = controller.get("image_dir")
        if image_dir:
            return str(image_dir)
    return "EvilEyeData"


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
    if not _database_enabled_in_config():
        return None
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


def _json_journal_available() -> bool:
    base_dir = Path(_image_base_dir())
    if not base_dir.is_dir():
        return False
    for subdir in ("Detections", "Events"):
        child = base_dir / subdir
        if child.is_dir() and any(child.iterdir()):
            return True
    return False


def journal_availability() -> dict[str, Any]:
    if _db_controller() is not None:
        return {
            "available": True,
            "mode": "database",
            "reason": "ok",
            "message": "",
        }
    if _json_journal_available():
        return {
            "available": True,
            "mode": "json",
            "reason": "json_fallback",
            "message": "Данные читаются из JSON-файлов (EvilEyeData), PostgreSQL не используется.",
        }
    if not _database_enabled_in_config():
        return {
            "available": False,
            "mode": "none",
            "reason": "database_disabled",
            "message": (
                "База данных отключена в конфигурации (controller.use_database: false). "
                "Включите use_database и настройте credentials.json, либо дождитесь записи JSON в EvilEyeData."
            ),
        }
    if not _database_config():
        return {
            "available": False,
            "mode": "none",
            "reason": "database_not_configured",
            "message": "PostgreSQL не настроена: отсутствует секция database в credentials.json.",
        }
    return {
        "available": False,
        "mode": "none",
        "reason": "database_unreachable",
        "message": "PostgreSQL настроена, но подключение не установлено.",
    }


def _unavailable_payload() -> dict[str, Any]:
    status = journal_availability()
    return {
        "available": False,
        "items": [],
        "total": 0,
        "mode": status.get("mode"),
        "reason": status.get("reason"),
        "message": status.get("message"),
    }


def _make_db_source(
        controller: DatabaseControllerPg,
        *,
        journal_type: str,
        date: str | None = None,
) -> DatabaseJournalDataSource:
    runtime_params = _runtime_params()
    adapters = create_event_journal_adapters(controller, runtime_params) if journal_type == "events" else None
    source = DatabaseJournalDataSource(
        controller,
        journal_type=journal_type,
        adapters=adapters,
        database_params={"database": _database_config()},
        params=runtime_params,
    )
    if date:
        source.set_date(date)
    return source


def _make_json_source(*, date: str | None = None) -> JsonLabelJournalDataSource:
    source = JsonLabelJournalDataSource(_image_base_dir(), params=_runtime_params())
    if date:
        source.set_date(date)
    return source


def _with_journal_meta(payload: dict[str, Any], *, mode: str) -> dict[str, Any]:
    enriched = dict(payload)
    enriched["mode"] = mode
    enriched.setdefault("reason", "ok" if mode == "database" else "json_fallback")
    if mode == "json":
        enriched.setdefault(
            "message",
            "Данные читаются из JSON-файлов (EvilEyeData), PostgreSQL не используется.",
        )
    return enriched


def load_events_page(*, page: int, size: int, filters: Dict[str, Any], date: str | None = None) -> dict[str, Any]:
    scoped_filters = _merge_current_filters(filters)
    controller = _db_controller()
    if controller is not None:
        source = _make_db_source(controller, journal_type="events", date=date)
        items = source.fetch(page, size, scoped_filters, sort=[("ts", "desc")])
        total = source.get_total(scoped_filters)
        return _with_journal_meta({"available": True, "items": items, "total": total}, mode="database")
    if not _json_journal_available():
        return _unavailable_payload()
    scoped_filters = {**scoped_filters, "journal_kind": "events"}
    source = _make_json_source(date=date)
    items = source.fetch(page, size, scoped_filters, sort=[("ts", "desc")])
    total = source.get_total(scoped_filters)
    return _with_journal_meta({"available": True, "items": items, "total": total}, mode="json")


def load_objects_page(*, page: int, size: int, filters: Dict[str, Any], date: str | None = None) -> dict[str, Any]:
    scoped_filters = _merge_current_filters(filters)
    controller = _db_controller()
    if controller is not None:
        source = _make_db_source(controller, journal_type="objects", date=date)
        items = source.fetch(page, size, scoped_filters, sort=[("ts", "desc")])
        total = source.get_total(scoped_filters)
        return _with_journal_meta({"available": True, "items": items, "total": total}, mode="database")
    if not _json_journal_available():
        return _unavailable_payload()
    scoped_filters = {**scoped_filters, "journal_kind": "objects"}
    source = _make_json_source(date=date)
    items = source.fetch(page, size, scoped_filters, sort=[("ts", "desc")])
    total = source.get_total(scoped_filters)
    return _with_journal_meta({"available": True, "items": items, "total": total}, mode="json")


def load_events_grouped_page(*, page: int, size: int, filters: Dict[str, Any], date: str | None = None) -> dict[str, Any]:
    payload = load_events_page(page=page, size=size, filters=filters, date=date)
    if not payload.get("available"):
        return payload
    grouped = group_events_rows(payload.get("items") or [])
    result = {"available": True, "items": grouped, "total": payload.get("total", len(grouped))}
    for key in ("mode", "reason", "message"):
        if key in payload:
            result[key] = payload[key]
    return result


def load_objects_grouped_page(*, page: int, size: int, filters: Dict[str, Any], date: str | None = None) -> dict[str, Any]:
    payload = load_objects_page(page=page, size=size, filters=filters, date=date)
    if not payload.get("available"):
        return payload
    grouped = group_objects_rows(payload.get("items") or [])
    result = {"available": True, "items": grouped, "total": payload.get("total", len(grouped))}
    for key in ("mode", "reason", "message"):
        if key in payload:
            result[key] = payload[key]
    return result


def resolve_journal_preview_path(*, path: str, date: str | None, journal_type: str) -> str | None:
    from evileye.visualization_modules.journal_path_resolver import JournalPathResolver

    event_data = {"date_folder": date} if date else None
    return JournalPathResolver.resolve_image_path(
        path,
        _image_base_dir(),
        event_data=event_data,
        journal_type=journal_type,
    )


def load_config_history(*, limit: int) -> dict[str, Any]:
    controller = _db_controller()
    if controller is None:
        status = journal_availability()
        return {
            "available": False,
            "items": [],
            "reason": status.get("reason"),
            "message": (
                "История конфигураций хранится только в PostgreSQL. "
                + str(status.get("message") or "База данных недоступна.")
            ),
        }
    manager = ConfigHistoryManager(controller)
    items = manager.get_config_history(limit=limit)
    current_run = get_current_run_summary()
    config_path = current_run.get("config_path") if current_run else None
    if config_path:
        items = [
            item for item in items
            if config_path in json.dumps(item.get("configuration_info") or {}, ensure_ascii=False)
        ]
    return {"available": True, "items": items, "mode": "database", "reason": "ok"}
