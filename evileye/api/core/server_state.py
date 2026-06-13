from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from evileye.api.core.config_run_access import get_config_run_manager
from evileye.api.core.runtime_registry import list_runtime_records, load_runtime_record, load_runtime_snapshot
from evileye.core.runtime_services import get_frame_broker


@dataclass
class ConfigSummary:
    pipeline_class: str | None
    source_items: list[dict[str, Any]]
    detector_count: int
    tracker_count: int
    event_detector_names: list[str]
    database_enabled: bool


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_pipeline_section(config: dict[str, Any]) -> dict[str, Any]:
    pipeline = config.get("pipeline")
    if isinstance(pipeline, dict):
        return pipeline
    return config


def load_config_summary(config_path: Optional[str]) -> ConfigSummary:
    if not config_path:
        return ConfigSummary(None, [], 0, 0, [], False)

    config = _load_json(Path(config_path))
    pipeline = _get_pipeline_section(config)
    sources = pipeline.get("sources") if isinstance(pipeline, dict) else None
    detectors = pipeline.get("detectors") if isinstance(pipeline, dict) else None
    trackers = pipeline.get("trackers") if isinstance(pipeline, dict) else None
    event_detectors = config.get("events_detectors") or pipeline.get("events_detectors") if isinstance(pipeline,
                                                                                                       dict) else {}
    database = config.get("database") or pipeline.get("database") if isinstance(pipeline, dict) else {}

    source_items: list[dict[str, Any]] = []
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        source_ids = source.get("source_ids") or []
        source_names = source.get("source_names") or []
        source_type = source.get("type") or source.get("source")
        camera_address = source.get("camera") or source.get("video") or source.get("path")
        if source_ids and source_names:
            for idx, source_id in enumerate(source_ids):
                source_items.append(
                    {
                        "source_id": source_id,
                        "source_name": source_names[idx] if idx < len(source_names) else f"Source {source_id}",
                        "source_type": source_type,
                        "address": camera_address,
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
    if not isinstance(database, dict):
        database = {}

    return ConfigSummary(
        pipeline_class=pipeline.get("pipeline_class") if isinstance(pipeline, dict) else None,
        source_items=source_items,
        detector_count=len(detectors or []),
        tracker_count=len(trackers or []),
        event_detector_names=sorted(event_detectors.keys()),
        database_enabled=bool(database),
    )


def _combined_runtime_records() -> Dict[int, Dict[str, Any]]:
    items = list_runtime_records()
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


def _read_log_tail(path: Path, *, lines: int = 120) -> list[str]:
    try:
        payload = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    return payload[-lines:]


def _run_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    config_summary = load_config_summary(record.get("config_path"))
    runtime_snapshot = load_runtime_snapshot(int(record.get("id") or 0)) if record.get("id") is not None else None
    rid = record.get("id")
    latest_frame_exists = _preview_frame_available(rid)
    return {
        "id": record.get("id"),
        "name": record.get("name"),
        "state": record.get("state"),
        "pid": record.get("pid"),
        "alive": bool(record.get("alive")),
        "managed": bool(record.get("managed")),
        "source": record.get("source"),
        "config_path": record.get("config_path"),
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
        "database_enabled": config_summary.database_enabled,
        "sources": config_summary.source_items,
        "runtime_snapshot": runtime_snapshot,
    }


def list_run_summaries() -> list[Dict[str, Any]]:
    return [_run_summary(record) for record in _combined_runtime_records().values()]


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


def _is_run_active(run: Dict[str, Any]) -> bool:
    state = str(run.get("state") or "")
    return bool(run.get("alive")) or state in {"starting", "running", "stopping"}


def list_active_run_summaries() -> list[Dict[str, Any]]:
    runs = [run for run in list_run_summaries() if _is_run_active(run)]
    runs.sort(
        key=lambda item: (
            _current_run_candidate_key(item),
            int(item.get("id") or 0),
        ),
        reverse=True,
    )
    return runs


def get_current_run_summary() -> Optional[Dict[str, Any]]:
    runs = list_active_run_summaries() or list_run_summaries()
    if not runs:
        return None
    return max(runs, key=_current_run_candidate_key)


def list_history_run_summaries(*, exclude_current: bool = True) -> list[Dict[str, Any]]:
    runs = list_run_summaries()
    current = get_current_run_summary()
    current_id = current.get("id") if current else None
    items = []
    for run in runs:
        if _is_run_active(run):
            continue
        if exclude_current and current_id is not None and run.get("id") == current_id:
            continue
        items.append(run)
    items.sort(key=lambda item: float(item.get("updated_at") or 0.0), reverse=True)
    return items


def list_camera_summaries(*, scope: str = "current") -> list[Dict[str, Any]]:
    cameras: list[Dict[str, Any]] = []
    if scope == "current":
        runs = [get_current_run_summary()]
    elif scope == "active":
        runs = list_active_run_summaries()
    else:
        runs = list_run_summaries()
    for run in runs:
        if not run:
            continue
        for source in run.get("sources", []):
            cameras.append(
                {
                    "run_id": run["id"],
                    "run_name": run.get("name"),
                    "run_state": run.get("state"),
                    "pipeline_class": run.get("pipeline_class"),
                    "source_id": source.get("source_id"),
                    "source_name": source.get("source_name"),
                    "source_type": source.get("source_type"),
                    "address": source.get("address"),
                    "preview_available": bool(
                        run.get("state") == "running"
                        and _preview_frame_available(run.get("id"), source.get("source_id"))
                    ),
                    "alive": bool(run.get("alive")),
                }
            )
    cameras.sort(key=lambda item: (item.get("run_id") or 0, str(item.get("source_name") or "")))
    return cameras


def _journal_stats() -> dict[str, Any]:
    try:
        from evileye.api.core.journal_service import load_events_page, load_objects_page

        events = load_events_page(page=0, size=1, filters={})
        objects = load_objects_page(page=0, size=1, filters={})
        if not events.get("available"):
            return {"available": False}
        return {
            "available": True,
            "events_total": int(events.get("total") or 0),
            "objects_total": int(objects.get("total") or 0),
        }
    except Exception:
        return {"available": False}


def build_overview() -> Dict[str, Any]:
    current_run = get_current_run_summary()
    active_runs = list_active_run_summaries()
    active_cameras = list_camera_summaries(scope="current")
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
    return {
        "timestamp": time.time(),
        "server": {
            "status": "ok",
            "current_run_id": current_run.get("id") if current_run else None,
            "current_run_state": current_state,
            "active_runs_total": len(active_runs),
            "cameras_total": len(active_cameras),
            "web_previews_available": sum(1 for camera in active_cameras if camera.get("preview_available")),
            "log_files": [path.name for path in log_files[:10]],
            "journal_stats": journal_stats,
        },
        "current_run": current_run,
        "active_runs": active_runs,
        "cameras": active_cameras,
        "latest_logs": latest_logs,
    }


def build_runtime_history() -> Dict[str, Any]:
    current_run = get_current_run_summary()
    return {
        "current_run": current_run,
        "active_runs": list_active_run_summaries(),
        "items": list_history_run_summaries(exclude_current=True),
    }


def iter_log_files() -> Iterable[Path]:
    return _log_files()
