from __future__ import annotations

import logging
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from evileye.api.core.config_run_access import get_config_run_manager
from evileye.api.core.runtime_registry import (
    list_runtime_record_stubs,
    list_runtime_records,
    load_runtime_record,
    load_runtime_snapshot,
    maybe_discover_process_runtimes,
)
from evileye.core.runtime_services import get_frame_broker

logger = logging.getLogger(__name__)


@dataclass
class ConfigSummary:
    pipeline_class: str | None
    source_items: list[dict[str, Any]]
    detector_count: int
    tracker_count: int
    event_detector_names: list[str]
    database_enabled: bool


_config_summary_cache: dict[str, tuple[float, ConfigSummary]] = {}
_EMPTY_CONFIG_SUMMARY = ConfigSummary(None, [], 0, 0, [], False)

def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def use_database_from_params(params: dict[str, Any] | None) -> bool:
    """Whether the run uses PostgreSQL (controller.use_database), not merely a database config section."""
    controller = params.get("controller") if isinstance(params, dict) else None
    if isinstance(controller, dict) and "use_database" in controller:
        return bool(controller.get("use_database"))
    return True


def storage_mode_from_params(params: dict[str, Any] | None) -> str:
    return "database" if use_database_from_params(params) else "json"


def _params_from_config_path(config_path: str | None) -> dict[str, Any]:
    if not config_path:
        return {}
    payload = _load_json(Path(config_path))
    return payload if isinstance(payload, dict) else {}


def effective_params_for_run(
        config_path: str | None,
        runtime_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    """Effective run config: live snapshot when present, else on-disk config file."""
    if isinstance(runtime_snapshot, dict):
        payload = runtime_snapshot.get("config")
        if isinstance(payload, dict):
            return payload
    return _params_from_config_path(config_path)


def _get_pipeline_section(config: dict[str, Any]) -> dict[str, Any]:
    pipeline = config.get("pipeline")
    if isinstance(pipeline, dict):
        return pipeline
    return config


def load_config_summary(config_path: Optional[str]) -> ConfigSummary:
    if not config_path:
        return _EMPTY_CONFIG_SUMMARY

    path = Path(config_path)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    cached = _config_summary_cache.get(config_path)
    if cached and cached[0] == mtime:
        return cached[1]

    config = _load_json(path)
    pipeline = _get_pipeline_section(config)
    sources = pipeline.get("sources") if isinstance(pipeline, dict) else None
    detectors = pipeline.get("detectors") if isinstance(pipeline, dict) else None
    trackers = pipeline.get("trackers") if isinstance(pipeline, dict) else None
    event_detectors = config.get("events_detectors") or pipeline.get("events_detectors") if isinstance(pipeline,
                                                                                                       dict) else {}

    source_items: list[dict[str, Any]] = []
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        source_ids = source.get("source_ids") or []
        source_names = source.get("source_names") or []
        source_type = source.get("type") or source.get("source")
        camera_address = source.get("camera") or source.get("video") or source.get("path")
        if source_ids and source_names:
            split = bool(source.get("split"))
            num_split = int(source.get("num_split") or len(source_names) or 0)
            src_coords_list = source.get("src_coords") or []
            parent_folder = "-".join(source_names[:num_split]) if split and num_split else None
            for idx, source_id in enumerate(source_ids):
                src_coords = None
                if split and idx < len(src_coords_list):
                    raw = src_coords_list[idx]
                    if isinstance(raw, (list, tuple)) and len(raw) >= 4:
                        src_coords = [int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3])]
                source_items.append(
                    {
                        "source_id": source_id,
                        "source_name": source_names[idx] if idx < len(source_names) else f"Source {source_id}",
                        "source_type": source_type,
                        "address": camera_address,
                        "split": split,
                        "parent_source_name": parent_folder,
                        "src_coords": src_coords,
                    }
                )
        else:
            source_items.append(
                {
                    "source_id": None,
                    "source_name": source.get("name") or source_type or "Source",
                    "source_type": source_type,
                    "address": camera_address,
                }
            )

    if not isinstance(event_detectors, dict):
        event_detectors = {}

    summary = ConfigSummary(
        pipeline_class=pipeline.get("pipeline_class") if isinstance(pipeline, dict) else None,
        source_items=source_items,
        detector_count=len(detectors or []),
        tracker_count=len(trackers or []),
        event_detector_names=sorted(event_detectors.keys()),
        database_enabled=use_database_from_params(config),
    )
    _config_summary_cache[config_path] = (mtime, summary)
    return summary


def _merge_manager_into_stub(stub: Dict[str, Any], item: Dict[str, Any]) -> Dict[str, Any]:
    merged = {**stub, **item}
    merged.setdefault("managed", True)
    merged.setdefault("source", "web")
    if "alive" not in item:
        merged["alive"] = merged.get("state") in {"starting", "running"}
    return merged


def _combined_runtime_stubs(*, discover: bool = False) -> Dict[int, Dict[str, Any]]:
    if discover:
        maybe_discover_process_runtimes()
    items = dict(list_runtime_record_stubs(discover=False))
    for rid, item in get_config_run_manager().list().items():
        existing = items.get(rid, {})
        items[rid] = _merge_manager_into_stub(existing, item)
    return dict(sorted(items.items(), key=lambda pair: pair[0]))


def _combined_runtime_records(*, discover: bool = True) -> Dict[int, Dict[str, Any]]:
    items = list_runtime_records(discover=discover)
    for rid, item in get_config_run_manager().list().items():
        existing = items.get(rid, {})
        merged = {**existing, **item}
        merged.setdefault("managed", True)
        merged.setdefault("source", "web")
        merged.setdefault("alive", merged.get("state") in {"starting", "running"})
        items[rid] = merged
    return dict(sorted(items.items(), key=lambda pair: pair[0]))


def _combined_runtime_record(rid: int) -> Optional[Dict[str, Any]]:
    record = load_runtime_record(rid)
    if record is None:
        try:
            record = get_config_run_manager().describe(rid)
        except KeyError:
            return None
    return record


def _log_files() -> list[Path]:
    logs_dir = Path("logs")
    if not logs_dir.exists():
        return []
    return sorted(logs_dir.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True)


_CAMERA_STALE_SEC = 5.0


def _preview_frame_available(run_id: int | None, source_id: int | None = None) -> bool:
    if run_id is None:
        return False
    try:
        broker = get_frame_broker()
        run_key = str(run_id)
        if source_id is not None and broker.latest_jpeg(f"{run_key}:{source_id}"):
            return True
        return bool(broker.latest_jpeg(run_key))
    except Exception:
        return False


def _frame_age_sec(run_id: int | None, source_id: int | None = None) -> float | None:
    if run_id is None:
        return None
    try:
        return get_frame_broker().get_frame_age_sec(str(run_id), source_id)
    except Exception:
        return None


def _source_is_working_from_snapshot(
    snapshot: dict[str, Any] | None,
    source_id: int | None,
) -> bool | None:
    """Return is_working from runtime snapshot when available; None if unknown."""
    if not isinstance(snapshot, dict) or source_id is None:
        return None
    sources = snapshot.get("sources")
    if not isinstance(sources, list):
        return None
    for entry in sources:
        if not isinstance(entry, dict):
            continue
        ids = entry.get("source_ids") or []
        try:
            if int(source_id) in {int(x) for x in ids}:
                if "is_working" in entry:
                    return bool(entry.get("is_working"))
                return None
        except Exception:
            continue
    return None


def _camera_health(
    run: dict[str, Any],
    source_id: int | None,
    *,
    stale_sec: float = _CAMERA_STALE_SEC,
) -> tuple[bool, float | None, bool, bool]:
    """Return (preview_available, last_frame_age_sec, is_working, reconnecting).

    ``is_working`` reflects capture health and does **not** require a JPEG in the
    FrameBroker. ``reconnecting`` is true only when the runtime snapshot reports
    ``is_working=False`` (real capture reconnect), not merely a missing preview.
    """
    rid = run.get("id")
    age = _frame_age_sec(rid, source_id)
    running = run.get("state") == "running"
    preview = bool(running and _preview_frame_available(rid, source_id))
    snap = run.get("runtime_snapshot") if isinstance(run.get("runtime_snapshot"), dict) else None
    snap_working = _source_is_working_from_snapshot(snap, source_id)

    if not running:
        is_working = False
    elif snap_working is not None:
        is_working = bool(snap_working)
    elif age is not None:
        is_working = age < stale_sec
    else:
        # Unknown snapshot and no broker frames: optimistic True so empty broker
        # does not mark every camera as reconnecting (cold-start / demand gap).
        is_working = True

    reconnecting = bool(running and snap_working is False)
    return preview, age, is_working, reconnecting


def _read_log_tail(path: Path, *, lines: int = 120) -> list[str]:
    try:
        payload = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    return payload[-lines:]


def _run_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    from evileye.api.core.log_service import resolve_run_log_files

    config_summary = load_config_summary(record.get("config_path"))
    runtime_snapshot = load_runtime_snapshot(int(record.get("id") or 0)) if record.get("id") is not None else None
    rid = record.get("id")
    latest_frame_exists = _preview_frame_available(rid)
    config_path = record.get("config_path")
    config_name = Path(config_path).name if config_path else None
    log_info = resolve_run_log_files(record)
    effective_params = effective_params_for_run(config_path, runtime_snapshot)
    database_enabled = use_database_from_params(effective_params)
    storage_mode = storage_mode_from_params(effective_params)
    return {
        "id": record.get("id"),
        "name": record.get("name"),
        "state": record.get("state"),
        "pid": record.get("pid"),
        "alive": bool(record.get("alive")),
        "managed": bool(record.get("managed")),
        "source": record.get("source"),
        "config_path": config_path,
        "config_name": config_name,
        "frame_dir": record.get("frame_dir"),
        "latest_frame_available": latest_frame_exists,
        "error": record.get("error"),
        "started_at": record.get("started_at"),
        "updated_at": record.get("updated_at"),
        "uptime_seconds": (
            max(0.0, time.time() - float(record.get("started_at")))
            if record.get("started_at") else None
        ),
        "pipeline_class": config_summary.pipeline_class,
        "detector_count": config_summary.detector_count,
        "tracker_count": config_summary.tracker_count,
        "event_detector_names": config_summary.event_detector_names,
        "database_enabled": database_enabled,
        "storage_mode": storage_mode,
        "sources": config_summary.source_items,
        "runtime_snapshot": runtime_snapshot,
        "log_session_id": log_info.get("log_session_id"),
        "log_files": log_info.get("log_files"),
        "log_match": log_info.get("log_match"),
    }


def list_run_summaries() -> list[Dict[str, Any]]:
    return [_run_summary(record) for record in _combined_runtime_records(discover=True).values()]


def _stub_to_list_item(stub: Dict[str, Any]) -> Dict[str, Any]:
    """UI list row from a registry stub: no snapshot, no config parse, no log scan."""
    config_path = stub.get("config_path")
    started = stub.get("started_at")
    item = dict(stub)
    item["config_name"] = Path(str(config_path)).name if config_path else None
    try:
        item["uptime_seconds"] = max(0.0, time.time() - float(started)) if started else None
    except (TypeError, ValueError):
        item["uptime_seconds"] = None
    return item


def _best_current_stub() -> Optional[Dict[str, Any]]:
    stubs = _combined_runtime_stubs(discover=False)
    if not stubs:
        return None
    active = [stub for stub in stubs.values() if _is_run_active(stub)]
    pool = active or list(stubs.values())
    return max(pool, key=_stub_candidate_key)


def get_current_run_list_item() -> Optional[Dict[str, Any]]:
    stub = _best_current_stub()
    return _stub_to_list_item(stub) if stub else None


def list_run_list_items(*, discover: bool = True) -> list[Dict[str, Any]]:
    stubs = _combined_runtime_stubs(discover=discover)
    items = [_stub_to_list_item(stub) for stub in stubs.values()]
    items.sort(
        key=lambda item: (float(item.get("updated_at") or 0.0), int(item.get("id") or 0)),
        reverse=True,
    )
    return items


def list_history_run_list_items(*, exclude_current: bool = True) -> list[Dict[str, Any]]:
    stubs = _combined_runtime_stubs(discover=False)
    current = _best_current_stub()
    current_id = int(current.get("id") or 0) if current else None
    items: list[Dict[str, Any]] = []
    for rid, stub in stubs.items():
        if _is_run_active(stub):
            continue
        if exclude_current and current_id is not None and rid == current_id:
            continue
        items.append(_stub_to_list_item(stub))
    items.sort(key=lambda item: float(item.get("updated_at") or 0.0), reverse=True)
    return items


def get_run_summary(rid: int) -> Optional[Dict[str, Any]]:
    runtime = _combined_runtime_record(rid)
    if runtime is None:
        return None
    return _run_summary(runtime)


def _current_run_candidate_key(run: Dict[str, Any]) -> tuple[int, int, float]:
    state = str(run.get("state") or "")
    state_rank = 2 if state == "running" else 1 if run.get("alive") else 0
    updated_at = float(run.get("updated_at") or 0.0)
    return (state_rank, 1 if bool(run.get("latest_frame_available")) else 0, updated_at)


def _stub_candidate_key(stub: Dict[str, Any]) -> tuple[int, float, int]:
    state = str(stub.get("state") or "")
    state_rank = 2 if state == "running" else 1 if stub.get("alive") else 0
    updated_at = float(stub.get("updated_at") or 0.0)
    return (state_rank, updated_at, int(stub.get("id") or 0))


def _is_run_active(run: Dict[str, Any]) -> bool:
    state = str(run.get("state") or "")
    if state == "stopping":
        return True
    return bool(run.get("alive")) and state in {"starting", "running"}


def list_active_run_summaries() -> list[Dict[str, Any]]:
    now = time.time()
    with _active_run_summaries_cache_lock:
        has_value = isinstance(_active_run_summaries_cache.value, list)
        decision = _swr_decide(_active_run_summaries_cache, now=now, has_value=has_value)
        cached = _active_run_summaries_cache.value if has_value else None
        if decision in {"fresh", "stale"}:
            return list(cached or [])
        if decision == "wait":
            if _active_run_summaries_cache.inflight_event is not None:
                _active_run_summaries_cache.inflight_event.wait(timeout=_STATE_FOLLOWER_WAIT_SEC)
            if isinstance(_active_run_summaries_cache.value, list):
                return _active_run_summaries_cache.value
            return []
        spawn_bg = decision == "stale_bg"
        stale_return = list(cached or []) if spawn_bg else None

    def _compute() -> list[Dict[str, Any]]:
        started_at = time.monotonic()
        runs: list[Dict[str, Any]] = []
        computed_ok = False
        try:
            stubs = _combined_runtime_stubs(discover=False)
            active_ids = [rid for rid, stub in stubs.items() if _is_run_active(stub)]
            for rid in active_ids:
                record = _combined_runtime_record(rid)
                if record is None:
                    continue
                runs.append(_run_summary(record))
            runs.sort(
                key=lambda item: (
                    _current_run_candidate_key(item),
                    int(item.get("id") or 0),
                ),
                reverse=True,
            )
            computed_ok = True
            return runs
        finally:
            total = time.monotonic() - started_at
            if total >= _STATE_LATENCY_WARN_SEC:
                logger.warning("list_active_run_summaries slow: %.3fs (runs=%d)", total, len(runs))
            with _active_run_summaries_cache_lock:
                ev = _active_run_summaries_cache.inflight_event
                _active_run_summaries_cache.inflight_event = None
                _active_run_summaries_cache.computing = False
                ts = time.time()
                if computed_ok:
                    _active_run_summaries_cache.value = runs
                    _active_run_summaries_cache.expires_at = ts + _STATE_CACHE_TTL_SEC
                    _active_run_summaries_cache.stale_expires_at = (
                        ts + _STATE_STALE_WHILE_REFRESH_TTL_SEC
                    )
                else:
                    _active_run_summaries_cache.value = None
                    _active_run_summaries_cache.expires_at = 0.0
                    _active_run_summaries_cache.stale_expires_at = 0.0
                if ev is not None:
                    ev.set()

    if spawn_bg:
        threading.Thread(target=_compute, daemon=True, name="active-runs-swr").start()
        return stale_return or []

    return _compute()


def get_current_config_path() -> Optional[str]:
    """Return config_path for the best current run without hydrating full summaries."""
    stubs = _combined_runtime_stubs(discover=False)
    if not stubs:
        return None
    active = [stub for stub in stubs.values() if _is_run_active(stub)]
    pool = active or list(stubs.values())
    best = max(pool, key=_stub_candidate_key)
    path = best.get("config_path")
    return str(path) if path else None


def get_current_run_summary() -> Optional[Dict[str, Any]]:
    now = time.time()
    with _current_run_cache_lock:
        has_value = _current_run_cache.value is not None
        decision = _swr_decide(_current_run_cache, now=now, has_value=has_value)
        cached = _current_run_cache.value
        cached_value: Dict[str, Any] | None = None if cached is _CACHED_NONE else cached  # type: ignore[assignment]
        if decision in {"fresh", "stale"}:
            return cached_value if has_value else None
        if decision == "wait":
            if _current_run_cache.inflight_event is not None:
                _current_run_cache.inflight_event.wait(timeout=_STATE_FOLLOWER_WAIT_SEC)
            cached = _current_run_cache.value
            return None if cached is _CACHED_NONE else cached
        spawn_bg = decision == "stale_bg"
        stale_return = cached_value if spawn_bg and has_value else None

    def _compute() -> Optional[Dict[str, Any]]:
        started_at = time.monotonic()
        computed_ok = False
        result: Optional[Dict[str, Any]] = None
        try:
            stubs = _combined_runtime_stubs(discover=False)
            if not stubs:
                result = None
            else:
                active = [stub for stub in stubs.values() if _is_run_active(stub)]
                pool = active or list(stubs.values())
                best = max(pool, key=_stub_candidate_key)
                rid = int(best.get("id") or 0)
                if not rid:
                    result = None
                else:
                    record = _combined_runtime_record(rid)
                    if record is None:
                        result = None
                    else:
                        result = _run_summary(record)
            computed_ok = True
            return result
        finally:
            total = time.monotonic() - started_at
            if total >= _STATE_LATENCY_WARN_SEC:
                logger.warning("get_current_run_summary slow: %.3fs", total)
            with _current_run_cache_lock:
                ev = _current_run_cache.inflight_event
                _current_run_cache.inflight_event = None
                _current_run_cache.computing = False
                ts = time.time()
                if computed_ok:
                    _current_run_cache.value = result if result is not None else _CACHED_NONE
                    _current_run_cache.expires_at = ts + _STATE_CACHE_TTL_SEC
                    _current_run_cache.stale_expires_at = ts + _STATE_STALE_WHILE_REFRESH_TTL_SEC
                else:
                    _current_run_cache.value = None
                    _current_run_cache.expires_at = 0.0
                    _current_run_cache.stale_expires_at = 0.0
                if ev is not None:
                    ev.set()

    if spawn_bg:
        threading.Thread(target=_compute, daemon=True, name="current-run-swr").start()
        return stale_return

    return _compute()


def list_history_run_summaries(*, exclude_current: bool = True) -> list[Dict[str, Any]]:
    stubs = _combined_runtime_stubs(discover=False)
    current = get_current_run_summary()
    current_id = current.get("id") if current else None
    items: list[Dict[str, Any]] = []
    for rid, stub in stubs.items():
        if _is_run_active(stub):
            continue
        if exclude_current and current_id is not None and rid == current_id:
            continue
        record = _combined_runtime_record(rid)
        if record is None:
            continue
        items.append(_run_summary(record))
    items.sort(key=lambda item: float(item.get("updated_at") or 0.0), reverse=True)
    return items


def _slim_snapshot_for_cameras(rid: int | None) -> dict[str, Any] | None:
    """Load runtime snapshot but keep only fields needed for camera health."""
    if rid is None:
        return None
    try:
        snapshot = load_runtime_snapshot(int(rid))
    except Exception:
        return None
    if not isinstance(snapshot, dict):
        return None
    sources = snapshot.get("sources")
    if not isinstance(sources, list):
        return {"sources": []}
    return {"sources": sources, "updated_at": snapshot.get("updated_at")}


def _slim_run_for_cameras(record: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal run view for /state/cameras — no logs, no full config snapshot."""
    config_summary = load_config_summary(record.get("config_path"))
    rid = record.get("id")
    return {
        "id": rid,
        "name": record.get("name"),
        "state": record.get("state"),
        "alive": bool(record.get("alive")),
        "pipeline_class": config_summary.pipeline_class,
        "sources": config_summary.source_items,
        "runtime_snapshot": _slim_snapshot_for_cameras(int(rid) if rid is not None else None),
    }


def _runs_for_camera_summaries(scope: str, *, discover: bool = False) -> list[Dict[str, Any]]:
    """Resolve runs for camera listing without hydrating full run summaries."""
    stubs = _combined_runtime_stubs(discover=discover)
    if not stubs:
        return []

    if scope == "current":
        active = [stub for stub in stubs.values() if _is_run_active(stub)]
        pool = active or list(stubs.values())
        best = max(pool, key=_stub_candidate_key)
        rid = int(best.get("id") or 0)
        if not rid:
            return []
        record = _combined_runtime_record(rid)
        if record is None:
            return []
        return [_slim_run_for_cameras(record)]

    if scope == "active":
        runs: list[Dict[str, Any]] = []
        for rid, stub in stubs.items():
            if not _is_run_active(stub):
                continue
            record = _combined_runtime_record(rid)
            if record is None:
                continue
            runs.append(_slim_run_for_cameras(record))
        return runs

    runs = []
    for rid in stubs:
        record = _combined_runtime_record(rid)
        if record is None:
            continue
        runs.append(_slim_run_for_cameras(record))
    return runs


def _swr_decide(
    item: "_TtlCacheItem",
    *,
    now: float,
    has_value: bool,
) -> str:
    """Return decision for stale-while-revalidate caches.

    - ``fresh``: serve cached value
    - ``stale_bg``: serve cached value and caller should start background refresh
    - ``stale``: serve cached value (refresh already in flight)
    - ``miss``: caller should compute synchronously (marks computing)
    - ``wait``: wait briefly for inflight then serve whatever is cached
    """
    if has_value and now < item.expires_at:
        return "fresh"
    if has_value and now < item.stale_expires_at:
        if item.computing:
            return "stale"
        item.computing = True
        item.inflight_event = threading.Event()
        item.inflight_event.clear()
        return "stale_bg"
    if item.computing:
        return "wait"
    item.computing = True
    item.inflight_event = threading.Event()
    item.inflight_event.clear()
    return "miss"


def list_camera_summaries(*, scope: str = "current") -> list[Dict[str, Any]]:
    now = time.time()
    with _camera_summaries_cache_lock:
        item = _camera_summaries_cache.get(scope)
        if item is None:
            item = _TtlCacheItem()
            _camera_summaries_cache[scope] = item

        has_value = isinstance(item.value, list)
        decision = _swr_decide(item, now=now, has_value=has_value)
        cached = item.value if has_value else None
        if decision in {"fresh", "stale"}:
            return list(cached or [])
        if decision == "wait":
            if item.inflight_event is not None:
                item.inflight_event.wait(timeout=_STATE_FOLLOWER_WAIT_SEC)
            if isinstance(item.value, list):
                return item.value
            return []
        # miss or stale_bg: computing flag already set
        spawn_bg = decision == "stale_bg"
        stale_return = list(cached or []) if spawn_bg else None

    def _compute() -> list[Dict[str, Any]]:
        started_at = time.monotonic()
        cameras: list[Dict[str, Any]] = []
        computed_ok = False
        try:
            runs = _runs_for_camera_summaries(scope, discover=False)
            for run in runs:
                if not run:
                    continue
                for source in run.get("sources", []):
                    sid = source.get("source_id")
                    preview, age, is_working, reconnecting = _camera_health(run, sid)
                    cameras.append(
                        {
                            "run_id": run["id"],
                            "run_name": run.get("name"),
                            "run_state": run.get("state"),
                            "pipeline_class": run.get("pipeline_class"),
                            "source_id": sid,
                            "source_name": source.get("source_name"),
                            "source_type": source.get("source_type"),
                            "address": source.get("address"),
                            "preview_available": preview,
                            "is_working": is_working,
                            "last_frame_age_sec": age,
                            "reconnecting": reconnecting,
                            "alive": bool(run.get("alive")),
                        }
                    )
            cameras.sort(key=lambda row: (row.get("run_id") or 0, str(row.get("source_name") or "")))
            total = time.monotonic() - started_at
            if total >= _STATE_LATENCY_WARN_SEC:
                logger.warning(
                    "list_camera_summaries(%s) slow: %.3fs (cameras=%d)",
                    scope,
                    total,
                    len(cameras),
                )
            computed_ok = True
            return cameras
        finally:
            with _camera_summaries_cache_lock:
                item.computing = False
                ev = item.inflight_event
                item.inflight_event = None
                if computed_ok:
                    item.value = cameras
                    ts = time.time()
                    item.expires_at = ts + _STATE_CACHE_TTL_SEC
                    item.stale_expires_at = ts + _STATE_STALE_WHILE_REFRESH_TTL_SEC
                else:
                    item.expires_at = 0.0
                    item.stale_expires_at = 0.0
                if ev is not None:
                    ev.set()

    if spawn_bg:
        threading.Thread(
            target=_compute,
            daemon=True,
            name=f"cameras-swr-{scope}",
        ).start()
        return stale_return or []

    return _compute()


_journal_stats_cache: tuple[float, dict[str, Any]] | None = None
_JOURNAL_STATS_TTL_SEC = 60

_STATE_CACHE_TTL_SEC = 6.0
_STATE_STALE_WHILE_REFRESH_TTL_SEC = 30.0
_STATE_FOLLOWER_WAIT_SEC = 0.25
_STATE_LATENCY_WARN_SEC = 1.0
_BACKGROUND_DISCOVER_INTERVAL_SEC = 5.0

_background_discover_stop = threading.Event()
_background_discover_thread: threading.Thread | None = None
_background_discover_lock = threading.Lock()


def start_background_runtime_discovery(*, interval_sec: float | None = None) -> None:
    """Periodic process discovery so hot state paths can use discover=False."""
    global _background_discover_thread
    interval = float(interval_sec) if interval_sec is not None else _BACKGROUND_DISCOVER_INTERVAL_SEC
    interval = max(1.0, interval)

    with _background_discover_lock:
        if _background_discover_thread is not None and _background_discover_thread.is_alive():
            return
        _background_discover_stop.clear()

        def _loop() -> None:
            # Prime once so first UI request sees live PIDs.
            try:
                maybe_discover_process_runtimes(force=True)
            except Exception:
                logger.debug("Initial runtime discovery failed", exc_info=True)
            while not _background_discover_stop.wait(interval):
                try:
                    maybe_discover_process_runtimes()
                except Exception:
                    logger.debug("Background runtime discovery failed", exc_info=True)

        _background_discover_thread = threading.Thread(
            target=_loop,
            daemon=True,
            name="RuntimeDiscovery",
        )
        _background_discover_thread.start()


def stop_background_runtime_discovery() -> None:
    global _background_discover_thread
    with _background_discover_lock:
        _background_discover_stop.set()
        thread = _background_discover_thread
        _background_discover_thread = None
    if thread is not None and thread.is_alive():
        thread.join(timeout=2.0)


@dataclass
class _TtlCacheItem:
    expires_at: float = 0.0
    stale_expires_at: float = 0.0
    value: Any | None = None
    computing: bool = False
    inflight_event: threading.Event | None = None


_overview_cache: _TtlCacheItem = _TtlCacheItem()
_overview_cache_lock = threading.Lock()

_camera_summaries_cache: dict[str, _TtlCacheItem] = {}
_camera_summaries_cache_lock = threading.Lock()

# Sentinel value to allow caching "no current run" without treating it as a cache miss.
_CACHED_NONE: Any = object()

_current_run_cache: _TtlCacheItem = _TtlCacheItem()
_current_run_cache_lock = threading.Lock()

_active_run_summaries_cache: _TtlCacheItem = _TtlCacheItem()
_active_run_summaries_cache_lock = threading.Lock()


def get_cached_overview() -> Dict[str, Any] | None:
    with _overview_cache_lock:
        if not isinstance(_overview_cache.value, dict):
            return None
        if time.time() >= _overview_cache.stale_expires_at:
            return None
        return _overview_cache.value


def get_cached_camera_summaries(scope: str) -> list[Dict[str, Any]] | None:
    with _camera_summaries_cache_lock:
        item = _camera_summaries_cache.get(scope)
        if not (item and isinstance(item.value, list)):
            return None
        if time.time() >= item.stale_expires_at:
            return None
        return item.value


def probe_cached_current_run_summary() -> tuple[bool, Dict[str, Any] | None]:
    """
    Returns (has_cached, cached_value).

    cached_value may be None when "no current run" was cached (not a cache miss).
    """
    now = time.time()
    with _current_run_cache_lock:
        if _current_run_cache.value is None:
            return False, None
        if now >= _current_run_cache.stale_expires_at:
            return False, None
        if _current_run_cache.value is _CACHED_NONE:
            return True, None
        if isinstance(_current_run_cache.value, dict):
            return True, _current_run_cache.value
        return False, None


def probe_cached_active_run_summaries() -> tuple[bool, list[Dict[str, Any]]]:
    """Returns (has_cached, cached_value)."""
    now = time.time()
    with _active_run_summaries_cache_lock:
        if not isinstance(_active_run_summaries_cache.value, list):
            return False, []
        if now >= _active_run_summaries_cache.stale_expires_at:
            return False, []
        return True, _active_run_summaries_cache.value


def _journal_stats() -> dict[str, Any]:
    global _journal_stats_cache
    now = time.time()
    if _journal_stats_cache is not None:
        cached_at, payload = _journal_stats_cache
        if now - cached_at < _JOURNAL_STATS_TTL_SEC:
            return payload
    try:
        import datetime
        from evileye.api.core.journal_service import load_journal_stats

        stats = load_journal_stats(date=datetime.date.today().isoformat())
        _journal_stats_cache = (now, stats)
        return stats
    except Exception:
        return {"available": False}


def _overview_placeholder() -> Dict[str, Any]:
    return {
        "timestamp": time.time(),
        "server": {"status": "ok", "log_files": [], "journal_stats": {"available": False}},
        "current_run": None,
        "active_runs": [],
        "cameras": [],
        "latest_logs": [],
    }


def build_overview() -> Dict[str, Any]:
    now = time.time()
    with _overview_cache_lock:
        has_value = isinstance(_overview_cache.value, dict)
        decision = _swr_decide(_overview_cache, now=now, has_value=has_value)
        cached = _overview_cache.value if has_value else None
        if decision in {"fresh", "stale"}:
            return cached  # type: ignore[return-value]
        if decision == "wait":
            if _overview_cache.inflight_event is not None:
                _overview_cache.inflight_event.wait(timeout=_STATE_FOLLOWER_WAIT_SEC)
            if isinstance(_overview_cache.value, dict):
                return _overview_cache.value
            return _overview_placeholder()
        spawn_bg = decision == "stale_bg"
        stale_return = cached if spawn_bg else None

    def _compute() -> Dict[str, Any]:
        started_at = time.monotonic()
        computed_ok = False
        result: Dict[str, Any] | None = None
        try:
            current_run = get_current_run_summary()
            active_runs = list_active_run_summaries()
            # Avoid extra nested `list_camera_summaries()` call here to prevent
            # duplicate expensive run/camera discovery work.
            active_cameras: list[Dict[str, Any]] = []
            if current_run:
                for source in current_run.get("sources", []):
                    sid = source.get("source_id")
                    preview, age, is_working, reconnecting = _camera_health(current_run, sid)
                    active_cameras.append(
                        {
                            "run_id": current_run["id"],
                            "run_name": current_run.get("name"),
                            "run_state": current_run.get("state"),
                            "pipeline_class": current_run.get("pipeline_class"),
                            "source_id": sid,
                            "source_name": source.get("source_name"),
                            "source_type": source.get("source_type"),
                            "address": source.get("address"),
                            "preview_available": preview,
                            "is_working": is_working,
                            "last_frame_age_sec": age,
                            "reconnecting": reconnecting,
                            "alive": bool(current_run.get("alive")),
                        }
                    )
                active_cameras.sort(
                    key=lambda item: (item.get("run_id") or 0, str(item.get("source_name") or ""))
                )
            log_files = _log_files()
            latest_logs = []
            for path in log_files[:3]:
                latest_logs.append(
                    {
                        "name": path.name,
                        "updated_at": path.stat().st_mtime,
                        "tail": _read_log_tail(path, lines=10),
                    }
                )

            current_state = current_run.get("state") if current_run else "stopped"
            journal_stats = _journal_stats()

            result = {
                "timestamp": time.time(),
                "server": {
                    "status": "ok",
                    "current_run_id": current_run.get("id") if current_run else None,
                    "current_run_state": current_state,
                    "active_runs_total": len(active_runs),
                    "cameras_total": len(active_cameras),
                    "web_previews_available": sum(
                        1 for camera in active_cameras if camera.get("preview_available")
                    ),
                    "log_files": [path.name for path in log_files[:10]],
                    "journal_stats": journal_stats,
                },
                "current_run": current_run,
                "active_runs": active_runs,
                "cameras": active_cameras,
                "latest_logs": latest_logs,
            }
            total = time.monotonic() - started_at
            if total >= _STATE_LATENCY_WARN_SEC:
                logger.warning("build_overview slow: %.3fs (cameras=%d)", total, len(active_cameras))

            computed_ok = True
            return result
        finally:
            with _overview_cache_lock:
                _overview_cache.computing = False
                ev = _overview_cache.inflight_event
                _overview_cache.inflight_event = None

                ts = time.time()
                if computed_ok and isinstance(result, dict):
                    _overview_cache.value = result
                    _overview_cache.expires_at = ts + _STATE_CACHE_TTL_SEC
                    _overview_cache.stale_expires_at = ts + _STATE_STALE_WHILE_REFRESH_TTL_SEC
                else:
                    _overview_cache.value = None
                    _overview_cache.expires_at = 0.0
                    _overview_cache.stale_expires_at = 0.0

                if ev is not None:
                    ev.set()

    if spawn_bg:
        threading.Thread(target=_compute, daemon=True, name="overview-swr").start()
        return stale_return if isinstance(stale_return, dict) else _overview_placeholder()

    return _compute()


def build_runtime_history() -> Dict[str, Any]:
    current_run = get_current_run_summary()
    return {
        "current_run": current_run,
        "active_runs": list_active_run_summaries(),
        "items": list_history_run_summaries(exclude_current=True),
    }


def iter_log_files() -> Iterable[Path]:
    return _log_files()
