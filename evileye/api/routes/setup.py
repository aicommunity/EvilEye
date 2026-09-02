"""First-run / basic setup API."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from evileye.api.core.setup_basic_merge import (
    apply_basic_setup,
    config_needs_setup,
    project_basic_from_config,
    recording_effectively_enabled,
    resolve_usable_data_dir,
)
from evileye.api.core.web_auth_bootstrap import user_must_change_password
from evileye.api.core.safe_paths import UnsafePathError, assert_under_dir, safe_config_name
from evileye.service_manager.minimal_config import ensure_system_config, minimal_system_config
from evileye.service_manager.state import load_state

router = APIRouter(prefix="/api/v1/setup", tags=["setup"])


class AlarmScheduleModel(BaseModel):
    enabled: bool = False
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)))
    periods: list[list[str]] = Field(default_factory=list)
    class_ids: list[int] = Field(default_factory=list)
    camera_cooldown_sec: int = 0


class BasicAlarmCameraModel(BaseModel):
    id: int = 0
    name: str = "Cam1"
    alarm_enabled: Optional[bool] = None
    alarm_schedule: Optional[AlarmScheduleModel] = None


class BasicSourceModel(BaseModel):
    id: int = 0
    name: str = "Cam1"
    type: str = "IpCamera"
    address: str | int = ""
    username: Optional[str] = None
    password: Optional[str] = None
    record: bool = True
    # Projection-only (split tails); ignored on apply.
    extra_names: Optional[list[str]] = None
    logical_ids: Optional[list[int]] = None
    # Deprecated: use alarm_cameras instead.
    alarm_enabled: Optional[bool] = None
    alarm_schedule: Optional[AlarmScheduleModel] = None


class BasicDatabaseModel(BaseModel):
    host_name: str = "localhost"
    port: int = 5432
    database_name: str = "evil_eye_db"
    user_name: str = "postgres"
    password: Optional[str] = None


class BasicSetupModel(BaseModel):
    config_name: str = "system.json"
    data_dir: str = ""
    storage_mode: str = "json"
    database: BasicDatabaseModel = Field(default_factory=BasicDatabaseModel)
    sources: list[BasicSourceModel] = Field(default_factory=list)
    analytics_enabled: bool = False
    recording_enabled: bool = False
    alarm_schedule: Optional[AlarmScheduleModel] = None
    alarm_cameras: list[BasicAlarmCameraModel] = Field(default_factory=list)


class DataDirPayload(BaseModel):
    path: str = Field(..., min_length=1)


class TestDbPayload(BaseModel):
    host_name: str = "localhost"
    port: int = 5432
    database_name: str = "evil_eye_db"
    user_name: str = "postgres"
    password: str = ""


def _configs_dir() -> Path:
    from evileye.core.paths import configs_dir
    cfg_dir = configs_dir()
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir


def _config_path(name: str) -> Path:
    safe = safe_config_name(name)
    return assert_under_dir(_configs_dir() / safe, _configs_dir())


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def _credentials_path() -> Path:
    from evileye.core.paths import creds_path
    return creds_path()


def _setup_section(creds: dict[str, Any]) -> dict[str, Any]:
    setup = creds.get("setup")
    if not isinstance(setup, dict):
        setup = {}
        creds["setup"] = setup
    setup.setdefault("data_dir_confirmed", False)
    setup.setdefault("completed", False)
    setup.setdefault("default_config", "system.json")
    return setup


def _default_config_name(creds: dict[str, Any]) -> str:
    setup = _setup_section(creds)
    name = str(setup.get("default_config") or "system.json")
    if not name.endswith(".json"):
        name += ".json"
    return name


def _has_sources(config: dict[str, Any]) -> bool:
    pipeline = config.get("pipeline") if isinstance(config.get("pipeline"), dict) else {}
    sources = pipeline.get("sources") if isinstance(pipeline, dict) else []
    return isinstance(sources, list) and len(sources) > 0


def _analytics_enabled(config: dict[str, Any]) -> bool:
    pipeline = config.get("pipeline") if isinstance(config.get("pipeline"), dict) else {}
    detectors = pipeline.get("detectors") or []
    trackers = pipeline.get("trackers") or []
    return bool(detectors or trackers)


def _build_status(config_name: Optional[str] = None) -> dict[str, Any]:
    creds = _load_json(_credentials_path())
    setup = _setup_section(creds)
    default_config = _default_config_name(creds)
    ensure_system_config(Path.cwd())
    name = config_name or default_config
    if not str(name).endswith(".json"):
        name = f"{name}.json"
    try:
        cfg_path = _config_path(name)
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    config = _load_json(cfg_path) if cfg_path.exists() else minimal_system_config()

    data_dir = resolve_usable_data_dir(config)
    has_sources = _has_sources(config)
    controller = config.get("controller") if isinstance(config.get("controller"), dict) else {}
    use_database = bool(controller.get("use_database", False))
    record = config.get("record") if isinstance(config.get("record"), dict) else {}
    recording_enabled = recording_effectively_enabled(config)

    needs_setup = config_needs_setup(config)
    configured = (not needs_setup) or bool(setup.get("completed")) or bool(setup.get("data_dir_confirmed"))
    ready_to_run = has_sources and (bool(data_dir) or bool(setup.get("data_dir_confirmed")))
    # Working configs with sources but no explicit data dir are still runnable (legacy paths).
    if has_sources and not ready_to_run:
        ready_to_run = True
    if use_database:
        db_creds = creds.get("database") if isinstance(creds.get("database"), dict) else {}
        ready_to_run = ready_to_run and bool(db_creds.get("password") or db_creds.get("admin_password"))

    must_change = False
    web_auth = creds.get("web_auth") if isinstance(creds.get("web_auth"), dict) else {}
    users = web_auth.get("users") if isinstance(web_auth.get("users"), list) else []
    for item in users:
        if isinstance(item, dict) and str(item.get("username") or "") == "admin":
            must_change = user_must_change_password(item)
            break

    svc_state = load_state(Path.cwd())
    return {
        "needs_setup": needs_setup,
        "configured": configured,
        "ready_to_run": ready_to_run,
        "must_change_password": must_change,
        "default_config": default_config,
        "config_name": cfg_path.name if cfg_path.exists() else name,
        "data_dir": data_dir,
        "data_dir_confirmed": bool(setup.get("data_dir_confirmed")) or bool(data_dir),
        "use_database": use_database,
        "has_sources": has_sources,
        "source_count": len((config.get("pipeline") or {}).get("sources") or []) if isinstance(config.get("pipeline"), dict) else 0,
        "analytics_enabled": _analytics_enabled(config),
        "recording_enabled": recording_enabled,
        "service": {
            "hint": "evileye service install",
            "installed": bool(svc_state.get("installed")) if svc_state else None,
        },
    }


@router.get("/status")
async def setup_status(config: Optional[str] = None) -> dict:
    return _build_status(config_name=config)


@router.get("/basic")
async def setup_basic_get(config: Optional[str] = None) -> dict:
    creds = _load_json(_credentials_path())
    name = config or _default_config_name(creds)
    ensure_system_config(Path.cwd())
    try:
        path = _config_path(name)
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.exists():
        _atomic_write(path, minimal_system_config())
    body = _load_json(path)
    return project_basic_from_config(body, creds, config_name=path.name)


@router.put("/basic")
async def setup_basic_put(payload: BasicSetupModel) -> dict:
    if payload.storage_mode not in {"json", "database"}:
        raise HTTPException(status_code=400, detail="storage_mode must be json or database")
    creds_path = _credentials_path()
    creds = _load_json(creds_path)
    name = payload.config_name or _default_config_name(creds)
    try:
        path = _config_path(name)
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = _load_json(path) if path.exists() else minimal_system_config()
    basic = payload.model_dump()
    new_config, new_creds = apply_basic_setup(existing, basic, creds)

    setup = _setup_section(new_creds)
    setup["default_config"] = path.name
    if str(payload.data_dir or "").strip():
        setup["data_dir_confirmed"] = True
    setup["completed"] = True

    _atomic_write(path, new_config)
    _atomic_write(creds_path, new_creds)

    status = _build_status(config_name=path.name)
    projected = project_basic_from_config(new_config, new_creds, config_name=path.name)
    return {"ok": True, "status": status, "basic": projected}


@router.post("/check-data-dir")
async def setup_check_data_dir(payload: DataDirPayload) -> dict:
    raw = payload.path.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="path is required")
    path = Path(raw).expanduser()
    created = False
    try:
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created = True
        if not path.is_dir():
            return {"ok": False, "writable": False, "free_bytes": 0, "message": "Path is not a directory", "created": created}
        probe = path / ".evileye_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        usage = shutil.disk_usage(path)
        return {
            "ok": True,
            "writable": True,
            "free_bytes": int(usage.free),
            "message": "Directory is writable",
            "created": created,
            "resolved": str(path.resolve()),
        }
    except Exception as exc:
        return {"ok": False, "writable": False, "free_bytes": 0, "message": str(exc), "created": created}


@router.post("/test-database")
async def setup_test_database(payload: TestDbPayload) -> dict:
    try:
        import psycopg2
    except Exception:
        try:
            import psycopg  # type: ignore

            conn = psycopg.connect(
                host=payload.host_name,
                port=payload.port,
                dbname=payload.database_name,
                user=payload.user_name,
                password=payload.password,
                connect_timeout=5,
            )
            conn.close()
            return {"ok": True, "message": "Connected"}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    try:
        conn = psycopg2.connect(
            host=payload.host_name,
            port=payload.port,
            dbname=payload.database_name,
            user=payload.user_name,
            password=payload.password,
            connect_timeout=5,
        )
        conn.close()
        return {"ok": True, "message": "Connected"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
