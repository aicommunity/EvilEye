import json
from pathlib import Path
from typing import List, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from evileye.api.core.config_run_access import get_config_run_manager
from evileye.api.core.public_base_url import resolve_public_api_base_url
from evileye.api.core.runtime_registry import list_runtime_records, load_runtime_record
from evileye.api.core.safe_paths import UnsafePathError, assert_under_dir, safe_config_name
from evileye.core.pipeline_configuration import mask_config_secrets as _mask_config_secrets
from evileye.core.pipeline_configuration import merge_preserving_secrets as _merge_preserving_secrets
from evileye.core.pipeline_configuration import write_config_with_backup

router = APIRouter(prefix="/api/v1/configs", tags=["configs"])


def _list_combined_runs() -> Dict[int, Dict]:
    from evileye.api.core.runtime_registry import merge_run_views

    items = list_runtime_records()
    for rid, item in get_config_run_manager().list().items():
        existing = items.get(rid)
        merged = merge_run_views(existing, item) or dict(item)
        merged.setdefault("managed", True)
        merged.setdefault("source", "web")
        merged.setdefault("alive", merged.get("state") in {"starting", "running"})
        items[rid] = merged
    return dict(sorted(items.items(), key=lambda pair: pair[0]))


class ConfigCreate(BaseModel):
    name: str = Field(..., description="Config file name, e.g. single_video.json")
    body: dict = Field(..., description="JSON configuration content")


class ConfigUpdate(BaseModel):
    body: dict = Field(..., description="JSON configuration content")


class ConfigRunCreate(BaseModel):
    name: Optional[str] = Field(None, description="Human-readable name (auto-generated if not provided)")
    config_name: Optional[str] = Field(None, description="Configuration name from the configs folder")
    config_body: Optional[dict] = Field(None, description="Configuration body, if file name not used")


def _configs_dir() -> Path:
    from evileye.core.paths import configs_dir

    cfg_dir = configs_dir()
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir


def _config_path(name: str) -> Path:
    safe = safe_config_name(name)
    return assert_under_dir(_configs_dir() / safe, _configs_dir())


@router.get("")
async def list_configs() -> List[str]:
    configs_dir = _configs_dir()
    if not configs_dir.exists():
        return []
    return sorted([p.name for p in configs_dir.glob("*.json")])


@router.get("/runs")
async def list_config_runs() -> Dict[int, Dict]:
    return _list_combined_runs()


@router.post("/runs")
async def create_config_run(payload: ConfigRunCreate) -> Dict:
    data = payload.model_dump()
    rid = get_config_run_manager().next_run_id()
    try:
        return get_config_run_manager().create(
            rid,
            data.get("name"),
            config_name=data.get("config_name"),
            config_body=data.get("config_body"),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Config file not found") from exc
    except (ValueError, UnsafePathError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/runs/{rid}")
async def get_config_run(rid: int) -> Dict:
    runtime = load_runtime_record(rid)
    try:
        current = get_config_run_manager().describe(rid)
        if runtime is not None:
            return {**runtime, **current}
        return current
    except KeyError as exc:
        if runtime is not None:
            return runtime
        raise HTTPException(status_code=404, detail="Config run not found") from exc


@router.post("/runs/{rid}/start")
async def start_config_run(rid: int, request: Request) -> Dict:
    try:
        api_base_url = resolve_public_api_base_url()
        return get_config_run_manager().start(rid, api_base_url=api_base_url)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Config run not found") from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/runs/{rid}/stop")
async def stop_config_run(rid: int) -> Dict:
    try:
        return get_config_run_manager().stop(rid)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Config run not found") from exc
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/runs/{rid}")
async def delete_config_run(rid: int) -> Dict:
    try:
        return get_config_run_manager().delete(rid)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Config run not found") from exc
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


def _mask_secrets(value):
    """Backward-compatible route helper using the shared config secret policy."""
    return _mask_config_secrets(value)


@router.get("/{name}")
async def get_config(name: str) -> dict:
    try:
        path = _config_path(name)
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Config not found")
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return _mask_secrets(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read config: {e}") from e


@router.post("")
async def create_config(payload: ConfigCreate):
    try:
        name = safe_config_name(payload.name)
        path = _config_path(name)
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if path.exists():
        raise HTTPException(status_code=409, detail="Config already exists")
    try:
        content = json.dumps(payload.body, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        write_config_with_backup(path, content, create_only=True)
        return {"name": name, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create config: {e}") from e


@router.put("/{name}")
async def update_config(name: str, payload: ConfigUpdate):
    try:
        target = _config_path(name)
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not target.exists():
        raise HTTPException(status_code=404, detail="Config not found")
    try:
        with open(target, "r", encoding="utf-8") as f:
            existing = json.load(f)
        if not isinstance(existing, dict):
            existing = {}
        body = _merge_preserving_secrets(existing, payload.body if isinstance(payload.body, dict) else {})
        content = json.dumps(body, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        write_config_with_backup(target, content)
        return {"name": target.name, "status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update config: {e}") from e


@router.delete("/{name}")
async def delete_config(name: str):
    try:
        target = _config_path(name)
    except UnsafePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not target.exists():
        raise HTTPException(status_code=404, detail="Config not found")
    try:
        target.unlink()
        return {"name": target.name, "status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete config: {e}") from e
