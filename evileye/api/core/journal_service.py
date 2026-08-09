from __future__ import annotations

import json
import os
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Optional

from evileye.api.core.journal_adapters_factory import create_event_journal_adapters
from evileye.api.core.journal_grouping import group_events_rows, group_objects_rows
from evileye.api.core.journal_time import normalize_row_times
from evileye.api.core.server_state import get_current_config_path
from evileye.database.config_history_manager import ConfigHistoryManager
from evileye.database_controller.database_controller_pg import DatabaseControllerPg
from evileye.visualization_modules.journal_data_source_db import DatabaseJournalDataSource
from evileye.visualization_modules.journal_data_source_json import JsonLabelJournalDataSource
from evileye.visualization_modules.journal_media_resolver import enrich_grouped_row, relative_to_base, row_key
from evileye.visualization_modules.journal_path_resolver import JournalPathResolver
from evileye.core.paths import configs_dir, creds_path


class JournalPathError(Exception):
    pass


class JournalPathForbidden(JournalPathError):
    pass


class JournalPathNotFound(JournalPathError):
    pass


class DateScopeError(ValueError):
    """Invalid journal date / date range query parameters."""
    pass


def _parse_iso_date(value: str) -> str:
    import datetime

    try:
        return datetime.date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise DateScopeError(f"Invalid date: {value}") from exc


def resolve_date_scope(
        *,
        date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
) -> dict[str, Any]:
    """Resolve date query params. Single `date` wins over range."""
    import datetime

    if date is not None and str(date).strip():
        raw = str(date).strip()
        if raw.lower() == "today":
            resolved = datetime.date.today().isoformat()
        else:
            resolved = _parse_iso_date(raw)
        return {"mode": "single", "date": resolved, "date_from": None, "date_to": None}

    df_raw = str(date_from).strip() if date_from is not None and str(date_from).strip() else None
    dt_raw = str(date_to).strip() if date_to is not None and str(date_to).strip() else None
    if df_raw or dt_raw:
        df = _parse_iso_date(df_raw) if df_raw else None
        dt = _parse_iso_date(dt_raw) if dt_raw else None
        if df is None:
            df = dt
        if dt is None:
            dt = df
        assert df is not None and dt is not None
        if df > dt:
            raise DateScopeError("date_from must be <= date_to")
        return {"mode": "range", "date": None, "date_from": df, "date_to": dt}

    return {"mode": "none", "date": None, "date_from": None, "date_to": None}


def _apply_date_scope(source: Any, scope: dict[str, Any]) -> None:
    mode = scope.get("mode")
    if mode == "single":
        source.set_date(scope.get("date"))
    elif mode == "range":
        source.set_date_range(scope.get("date_from"), scope.get("date_to"))
    else:
        if hasattr(source, "set_date_range"):
            source.set_date_range(None, None)
        source.set_date(None)


_db_controller_cache: DatabaseControllerPg | None = None
_db_controller_failed: bool = False
_grouped_row_cache: dict[str, dict[str, dict[str, Any]]] = {"events": {}, "objects": {}}
_json_source_cache: dict[tuple[str, str | None], JsonLabelJournalDataSource] = {}
_runtime_params_cache: tuple[str, float, dict[str, Any]] | None = None
_image_base_dir_cache: tuple[str, float, str] | None = None
_light_config_path_cache: tuple[float, str | None] | None = None
_LIGHT_CONFIG_PATH_TTL_SEC = 5.0
_path_resolve_cache: OrderedDict[tuple[str, ...], str | None] = OrderedDict()
_PATH_RESOLVE_CACHE_MAX = 4096


def assert_path_under_base(resolved: str, base_dir: str) -> str:
    from evileye.api.core.safe_paths import UnsafePathError, assert_under_dir

    try:
        target = assert_under_dir(resolved, base_dir)
    except UnsafePathError as exc:
        raise JournalPathForbidden(str(exc)) from exc
    if not target.is_file():
        raise JournalPathNotFound("File not found")
    return str(target)


def _load_credentials() -> dict[str, Any]:
    path = creds_path()
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


def _config_mtime(config_path: str | None) -> float:
    if not config_path:
        return 0.0
    try:
        return os.path.getmtime(config_path)
    except OSError:
        return 0.0


def _current_config_path() -> str | None:
    """Resolve current config path without hydrating full run summaries."""
    global _light_config_path_cache
    now = time.time()
    if _light_config_path_cache is not None:
        cached_at, cached_path = _light_config_path_cache
        if now - cached_at < _LIGHT_CONFIG_PATH_TTL_SEC:
            return cached_path
    path = get_current_config_path()
    _light_config_path_cache = (now, path)
    return path


def _load_runtime_params_uncached() -> dict[str, Any]:
    config_path = _current_config_path()
    if not config_path:
        return {}
    try:
        payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _runtime_params() -> dict[str, Any]:
    global _runtime_params_cache
    config_path = _current_config_path() or ""
    mtime = _config_mtime(config_path or None)
    if _runtime_params_cache and _runtime_params_cache[0] == config_path and _runtime_params_cache[1] == mtime:
        return _runtime_params_cache[2]
    params = _load_runtime_params_uncached()
    _runtime_params_cache = (config_path, mtime, params)
    return params


def _database_enabled_in_config() -> bool:
    params = _runtime_params()
    controller = params.get("controller") if isinstance(params, dict) else None
    if isinstance(controller, dict) and "use_database" in controller:
        return bool(controller.get("use_database"))
    return True


def _image_base_dir() -> str:
    global _image_base_dir_cache
    config_path = _current_config_path() or ""
    mtime = _config_mtime(config_path or None)
    if _image_base_dir_cache and _image_base_dir_cache[0] == config_path and _image_base_dir_cache[1] == mtime:
        return _image_base_dir_cache[2]
    params = _runtime_params()
    image_dir = "EvilEyeData"
    database = params.get("database") if isinstance(params, dict) else None
    if isinstance(database, dict):
        configured = database.get("image_dir") or database.get("images_dir")
        if configured:
            image_dir = str(configured)
    if image_dir == "EvilEyeData":
        controller = params.get("controller") if isinstance(params, dict) else None
        if isinstance(controller, dict):
            configured = controller.get("image_dir")
            if configured:
                image_dir = str(configured)
    if image_dir == "EvilEyeData":
        record = params.get("record") if isinstance(params, dict) else None
        if isinstance(record, dict) and record.get("out_dir"):
            image_dir = str(record["out_dir"])
    _image_base_dir_cache = (config_path, mtime, image_dir)
    return image_dir


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


def _source_mappings() -> dict[str, tuple[Any, Any]]:
    mappings: dict[str, tuple[Any, Any]] = {}
    params = _runtime_params()
    pipeline = params.get("pipeline") if isinstance(params, dict) else None
    if not isinstance(pipeline, dict):
        pipeline = params
    for source in (pipeline.get("sources") if isinstance(pipeline, dict) else None) or []:
        if not isinstance(source, dict):
            continue
        address = source.get("camera") or source.get("video") or source.get("path") or ""
        source_ids = source.get("source_ids") or []
        source_names = source.get("source_names") or []
        for source_id, source_name in zip(source_ids, source_names):
            mappings[str(source_name)] = (source_id, address)
    return mappings


def _enrich_rows(
        rows: list[dict[str, Any]],
        *,
        journal_type: str,
        list_mode: bool = True,
        cache_rows: bool = False,
        meta_only: bool = False,
) -> list[dict[str, Any]]:
    base_dir = _image_base_dir()
    mappings = _source_mappings()
    enriched_rows: list[dict[str, Any]] = []
    for row in rows:
        if cache_rows:
            _grouped_row_cache.setdefault(journal_type, {})[row_key(row)] = dict(row)
        enriched_rows.append(
            normalize_row_times(
                enrich_grouped_row(
                    row,
                    base_dir=base_dir,
                    journal_type=journal_type,
                    source_mappings=mappings,
                    include_raw_events=not list_mode,
                    list_mode=list_mode,
                    meta_only=meta_only,
                )
            )
        )
    return enriched_rows


_filters_meta_cache: tuple[float, dict[str, Any]] | None = None
_FILTERS_META_TTL_SEC = 60.0
_journal_stats_page_cache: dict[tuple[str | None, str | None, str | None], tuple[float, dict[str, Any]]] = {}
_JOURNAL_STATS_PAGE_TTL_SEC = 20.0
_FILTERS_META_MAX_DATES = 60


def load_filters_meta() -> dict[str, Any]:
    global _filters_meta_cache
    now = time.time()
    if _filters_meta_cache is not None:
        cached_at, payload = _filters_meta_cache
        if now - cached_at < _FILTERS_META_TTL_SEC:
            return payload

    dates: list[str] = []
    try:
        controller = _db_controller()
        if controller is not None:
            source = _make_db_source(controller, journal_type="events")
            if hasattr(source, "list_available_dates"):
                dates = list(source.list_available_dates())
        elif _json_journal_available():
            source = _make_json_source()
            dates = list(source.list_available_dates())
    except Exception:
        dates = []
    # Newest dates last in many adapters; keep the most recent N for UI dropdowns.
    if len(dates) > _FILTERS_META_MAX_DATES:
        dates = sorted(dates)[-_FILTERS_META_MAX_DATES:]
    payload = {
        "dates": dates,
        "source_names": sorted(_current_source_names()),
        "event_types_events": [
            "attr_found", "attr_lost", "zone_entered", "zone_left",
            "fov_found", "fov_lost", "cam", "sys",
        ],
        "event_types_objects": ["found", "lost"],
    }
    _filters_meta_cache = (now, payload)
    return payload


def _merge_current_filters(
    filters: Dict[str, Any],
    *,
    journal_kind: str | None = None,
) -> Dict[str, Any]:
    """Merge implicit run-scope filters.

    Events include System rows (``source_name='System'``). Auto-scoping to
    camera names would hide them, so events keep caller filters only.
    Objects still default to current pipeline source names.
    """
    merged = dict(filters)
    if journal_kind == "events":
        return merged
    source_names = _current_source_names()
    if source_names and "source_name" not in merged and "source_names" not in merged:
        merged["source_names"] = sorted(source_names)
    return merged


def _db_controller() -> Optional[DatabaseControllerPg]:
    global _db_controller_cache, _db_controller_failed
    if _db_controller_failed:
        return None
    if _db_controller_cache is not None:
        try:
            if _db_controller_cache.is_connected():
                return _db_controller_cache
        except Exception:
            _db_controller_cache = None
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
            _db_controller_failed = True
            return None
        _db_controller_cache = controller
        return controller
    except Exception:
        _db_controller_failed = True
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
        date_from: str | None = None,
        date_to: str | None = None,
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
    scope = resolve_date_scope(date=date, date_from=date_from, date_to=date_to)
    _apply_date_scope(source, scope)
    return source


def _get_json_source(
        *,
        date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
) -> JsonLabelJournalDataSource:
    base_dir = _image_base_dir()
    scope = resolve_date_scope(date=date, date_from=date_from, date_to=date_to)
    cache_key = (base_dir, scope.get("date"), scope.get("date_from"), scope.get("date_to"))
    source = _json_source_cache.get(cache_key)
    if source is None:
        source = JsonLabelJournalDataSource(base_dir, params=_runtime_params())
        _apply_date_scope(source, scope)
        _json_source_cache[cache_key] = source
        return source
    source.set_base_dir(base_dir)
    source.params = _runtime_params()
    _apply_date_scope(source, scope)
    return source


def _make_json_source(
        *,
        date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
) -> JsonLabelJournalDataSource:
    return _get_json_source(date=date, date_from=date_from, date_to=date_to)


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


def load_events_page(
        *,
        page: int,
        size: int,
        filters: Dict[str, Any],
        date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
) -> dict[str, Any]:
    scoped_filters = _merge_current_filters(filters, journal_kind="events")
    controller = _db_controller()
    if controller is not None:
        source = _make_db_source(
            controller, journal_type="events", date=date, date_from=date_from, date_to=date_to,
        )
        items = source.fetch(page, size, scoped_filters, sort=[("ts", "desc")])
        total = source.get_total(scoped_filters)
        return _with_journal_meta({"available": True, "items": items, "total": total}, mode="database")
    if not _json_journal_available():
        return _unavailable_payload()
    scoped_filters = {**scoped_filters, "journal_kind": "events"}
    source = _get_json_source(date=date, date_from=date_from, date_to=date_to)
    source.begin_request()
    items = source.fetch(page, size, scoped_filters, sort=[("ts", "desc")])
    total = source.get_total(scoped_filters)
    return _with_journal_meta({"available": True, "items": items, "total": total}, mode="json")


def load_objects_page(
        *,
        page: int,
        size: int,
        filters: Dict[str, Any],
        date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
) -> dict[str, Any]:
    scoped_filters = _merge_current_filters(filters, journal_kind="objects")
    controller = _db_controller()
    if controller is not None:
        source = _make_db_source(
            controller, journal_type="objects", date=date, date_from=date_from, date_to=date_to,
        )
        items = source.fetch(page, size, scoped_filters, sort=[("ts", "desc")])
        total = source.get_total(scoped_filters)
        return _with_journal_meta({"available": True, "items": items, "total": total}, mode="database")
    if not _json_journal_available():
        return _unavailable_payload()
    scoped_filters = {**scoped_filters, "journal_kind": "objects"}
    source = _get_json_source(date=date, date_from=date_from, date_to=date_to)
    source.begin_request()
    items = source.fetch(page, size, scoped_filters, sort=[("ts", "desc")])
    total = source.get_total(scoped_filters)
    return _with_journal_meta({"available": True, "items": items, "total": total}, mode="json")


def load_events_grouped_page(
        *,
        page: int,
        size: int,
        filters: Dict[str, Any],
        date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
) -> dict[str, Any]:
    # Group-then-paginate: over-fetch raw rows, group, then slice grouped page.
    need_groups = (page + 1) * size
    raw_needed = min(max(need_groups * 3, size * 4, 120), 2000)
    payload = load_events_page(
        page=0, size=raw_needed, filters=filters, date=date, date_from=date_from, date_to=date_to,
    )
    if not payload.get("available"):
        return payload
    grouped = _enrich_rows(
        group_events_rows(payload.get("items") or []),
        journal_type="events",
        list_mode=True,
        cache_rows=True,
    )
    start = page * size
    sliced = grouped[start : start + size]
    raw_total = int(payload.get("total") or 0)
    # If we scanned all raw rows, grouped length is authoritative; else estimate.
    if raw_total <= raw_needed:
        total_grouped = len(grouped)
    else:
        total_grouped = max(len(grouped), raw_total // 2)
    has_more = (start + size) < total_grouped or raw_total > raw_needed
    result = {
        "available": True,
        "items": sliced,
        "total": total_grouped,
        "page": page,
        "size": size,
        "has_more": has_more,
    }
    for key in ("mode", "reason", "message"):
        if key in payload:
            result[key] = payload[key]
    return result


def load_objects_grouped_page(
        *,
        page: int,
        size: int,
        filters: Dict[str, Any],
        date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
) -> dict[str, Any]:
    need_groups = (page + 1) * size
    raw_needed = min(max(need_groups * 3, size * 4, 120), 2000)
    payload = load_objects_page(
        page=0, size=raw_needed, filters=filters, date=date, date_from=date_from, date_to=date_to,
    )
    if not payload.get("available"):
        return payload
    grouped = _enrich_rows(
        group_objects_rows(payload.get("items") or []),
        journal_type="objects",
        list_mode=True,
        cache_rows=True,
    )
    start = page * size
    sliced = grouped[start : start + size]
    raw_total = int(payload.get("total") or 0)
    if raw_total <= raw_needed:
        total_grouped = len(grouped)
    else:
        total_grouped = max(len(grouped), raw_total // 2)
    has_more = (start + size) < total_grouped or raw_total > raw_needed
    result = {
        "available": True,
        "items": sliced,
        "total": total_grouped,
        "page": page,
        "size": size,
        "has_more": has_more,
    }
    for key in ("mode", "reason", "message"):
        if key in payload:
            result[key] = payload[key]
    return result


def load_journal_stats(
        *,
        date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
) -> dict[str, Any]:
    import datetime

    has_explicit = bool(
        (date and str(date).strip())
        or (date_from and str(date_from).strip())
        or (date_to and str(date_to).strip())
    )
    if not has_explicit:
        date = datetime.date.today().isoformat()

    cache_key = (date, date_from, date_to)
    now = time.time()
    cached = _journal_stats_page_cache.get(cache_key)
    if cached is not None:
        cached_at, payload = cached
        if now - cached_at < _JOURNAL_STATS_PAGE_TTL_SEC:
            return payload

    scope = resolve_date_scope(date=date, date_from=date_from, date_to=date_to)
    scoped_filters: dict[str, Any] = {}
    if scope["mode"] == "single":
        scoped_filters["date_folder"] = scope["date"]

    controller = _db_controller()
    if controller is not None:
        events_source = _make_db_source(
            controller,
            journal_type="events",
            date=date,
            date_from=date_from,
            date_to=date_to,
        )
        objects_source = _make_db_source(
            controller,
            journal_type="objects",
            date=date,
            date_from=date_from,
            date_to=date_to,
        )
        events_filters = {**scoped_filters, "journal_kind": "events"}
        objects_filters = {**scoped_filters, "journal_kind": "objects"}
        payload = {
            "available": True,
            "events_total": int(events_source.get_total(events_filters)),
            "objects_total": int(objects_source.get_total(objects_filters)),
        }
        _journal_stats_page_cache[cache_key] = (now, payload)
        return payload

    if not _json_journal_available():
        return {"available": False}

    source = _get_json_source(date=date, date_from=date_from, date_to=date_to)
    source.begin_request()
    events_total = source.get_total({**scoped_filters, "journal_kind": "events"})
    objects_total = source.get_total({**scoped_filters, "journal_kind": "objects"})
    payload = {
        "available": True,
        "events_total": int(events_total),
        "objects_total": int(objects_total),
    }
    _journal_stats_page_cache[cache_key] = (now, payload)
    return payload


def load_row_meta(*, row_key_value: str, journal_type: str, meta_only: bool = True) -> dict[str, Any]:
    cached = _grouped_row_cache.get(journal_type, {}).get(row_key_value)
    if not cached:
        raise JournalPathNotFound("Row not found in cache")
    enriched = _enrich_rows(
        [cached],
        journal_type=journal_type,
        list_mode=False,
        meta_only=meta_only,
    )[0]
    return {
        "row_key": enriched.get("row_key"),
        "bbox_found": enriched.get("bbox_found"),
        "bbox_lost": enriched.get("bbox_lost"),
        "zone_coords": enriched.get("zone_coords"),
        "has_found_video": enriched.get("has_found_video"),
        "has_lost_video": enriched.get("has_lost_video"),
        "has_stream_video": enriched.get("has_stream_video"),
        "found_video_path": enriched.get("found_video_path"),
        "lost_video_path": enriched.get("lost_video_path"),
        "stream_video_path": enriched.get("stream_video_path"),
        "stream_offset_seconds": enriched.get("stream_offset_seconds"),
    }


def _cached_path_resolve(cache_key: tuple[str, ...], resolver) -> str | None:
    cached = _path_resolve_cache.get(cache_key)
    if cache_key in _path_resolve_cache:
        _path_resolve_cache.move_to_end(cache_key)
        return cached
    resolved = resolver()
    _path_resolve_cache[cache_key] = resolved
    if len(_path_resolve_cache) > _PATH_RESOLVE_CACHE_MAX:
        _path_resolve_cache.popitem(last=False)
    return resolved


def resolve_journal_preview_path(
        *,
        path: str,
        date: str | None,
        journal_type: str,
        mode: str = "found",
) -> str | None:
    preview_mode = "lost" if str(mode).lower() == "lost" else "found"
    cache_key = ("preview", path, date or "", journal_type, preview_mode)
    return _cached_path_resolve(
        cache_key,
        lambda: _resolve_journal_preview_path_uncached(
            path=path,
            date=date,
            journal_type=journal_type,
            mode=mode,
        ),
    )


def _resolve_journal_preview_path_uncached(
        *,
        path: str,
        date: str | None,
        journal_type: str,
        mode: str = "found",
) -> str | None:
    preview_mode = "lost" if str(mode).lower() == "lost" else "found"
    event_data: dict[str, str] = {"preview_mode": preview_mode}
    if date:
        event_data["date_folder"] = date
    return JournalPathResolver.resolve_image_path(
        path,
        _image_base_dir(),
        event_data=event_data,
        journal_type=journal_type,
    )


def resolve_journal_frame_path(
        *,
        path: str,
        date: str | None,
        journal_type: str,
        mode: str = "found",
) -> str | None:
    cache_key = ("frame", path, date or "", journal_type, str(mode).lower())
    return _cached_path_resolve(
        cache_key,
        lambda: _resolve_journal_frame_path_uncached(
            path=path,
            date=date,
            journal_type=journal_type,
            mode=mode,
        ),
    )


def _resolve_journal_frame_path_uncached(
        *,
        path: str,
        date: str | None,
        journal_type: str,
        mode: str = "found",
) -> str | None:
    preview = _resolve_journal_preview_path_uncached(
        path=path,
        date=date,
        journal_type=journal_type,
        mode=mode,
    )
    if not preview:
        return None
    frame = JournalPathResolver.resolve_frame_path(preview, journal_type=journal_type)
    return frame or preview


def resolve_journal_video_path(*, path: str | None = None) -> str | None:
    if not path:
        return None
    base_dir = _image_base_dir()
    candidate = path
    if not os.path.isabs(candidate):
        candidate = os.path.join(base_dir, path)
    if os.path.isfile(candidate):
        return candidate
    return None


def resolve_secured_journal_file(*, resolver) -> str:
    resolved = resolver()
    if not resolved:
        raise JournalPathNotFound("Media file not found")
    return assert_path_under_base(resolved, _image_base_dir())


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
    config_path = _current_config_path()
    if config_path:
        items = [
            item for item in items
            if config_path in json.dumps(item.get("configuration_info") or {}, ensure_ascii=False)
        ]
    return {"available": True, "items": items, "mode": "database", "reason": "ok"}


def compare_config_history(job_id1: int, job_id2: int) -> dict[str, Any]:
    controller = _db_controller()
    if controller is None:
        return {"available": False, "error": "Database unavailable"}
    manager = ConfigHistoryManager(controller)
    result = manager.compare_configurations(job_id1, job_id2)
    c1 = manager.get_config_by_job_id(job_id1)
    c2 = manager.get_config_by_job_id(job_id2)
    result["left"] = (c1 or {}).get("configuration_info")
    result["right"] = (c2 or {}).get("configuration_info")
    result["available"] = True
    return result


def restore_config_history(job_id: int, target_name: str) -> dict[str, Any]:
    safe = Path(target_name).name
    if safe != target_name or ".." in target_name:
        raise ValueError("Invalid target config name")
    target = configs_dir() / safe
    if not target.parent.exists():
        raise FileNotFoundError("configs directory not found")
    controller = _db_controller()
    if controller is None:
        raise ValueError("Database unavailable for restore")
    manager = ConfigHistoryManager(controller)
    result = manager.restore_configuration(job_id, str(target), create_backup=True)
    if not result.get("success"):
        raise ValueError(result.get("error") or "Restore failed")
    return result
