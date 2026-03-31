import json
from pathlib import Path
from typing import List, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from evileye.api.core.config_run_access import get_config_run_manager

router = APIRouter(prefix="/api/v1/configs", tags=["configs"])


class ConfigCreate(BaseModel):
    name: str = Field(..., description="Config file name, e.g. single_video.json")
    body: dict = Field(..., description="JSON configuration content")


class ConfigUpdate(BaseModel):
    body: dict = Field(..., description="JSON configuration content")


class ConfigRunCreate(BaseModel):
    name: Optional[str] = Field(None, description="Human-readable name (auto-generated if not provided)")
    config_name: Optional[str] = Field(None, description="Configuration name from the configs folder")
    config_body: Optional[dict] = Field(None, description="Configuration body, if file name not used")


# ── Config file CRUD ────────────────────────────────────────────────

@router.get("")
async def list_configs() -> List[str]:
    configs_dir = Path("configs")
    if not configs_dir.exists():
        return []
    return sorted([p.name for p in configs_dir.glob("*.json")])


# Маршруты /runs объявлены до /{name}, иначе GET /configs/runs матчится как get_config(name="runs")
@router.get("/runs")
async def list_config_runs() -> Dict[int, Dict]:
    return get_config_run_manager().list()


@router.post("/runs")
async def create_config_run(payload: ConfigRunCreate) -> Dict:
    data = payload.model_dump()
    rid = len(get_config_run_manager().list()) + 1
    try:
        return get_config_run_manager().create(
            rid,
            data.get("name"),
            config_name=data.get("config_name"),
            config_body=data.get("config_body"),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Config file not found") from exc
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/runs/{rid}")
async def get_config_run(rid: int) -> Dict:
    try:
        return get_config_run_manager().describe(rid)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Config run not found") from exc


@router.post("/runs/{rid}/start")
async def start_config_run(rid: int) -> Dict:
    try:
        return get_config_run_manager().start(rid)
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


@router.get("/{name}")
async def get_config(name: str) -> dict:
    path = Path("configs") / name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Config not found")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read config: {e}") from e


@router.post("")
async def create_config(payload: ConfigCreate):
    name = Path(payload.name).name
    if not name.endswith(".json"):
        raise HTTPException(status_code=400, detail="Config name must end with .json")
    cfg_dir = Path("configs")
    cfg_dir.mkdir(parents=True, exist_ok=True)
    path = cfg_dir / name
    if path.exists():
        raise HTTPException(status_code=409, detail="Config already exists")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload.body, f, ensure_ascii=False, indent=2)
        return {"name": name, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create config: {e}") from e


@router.put("/{name}")
async def update_config(name: str, payload: ConfigUpdate):
    target = Path("configs") / Path(name).name
    if not target.exists():
        raise HTTPException(status_code=404, detail="Config not found")
    try:
        with open(target, "w", encoding="utf-8") as f:
            json.dump(payload.body, f, ensure_ascii=False, indent=2)
        return {"name": target.name, "status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update config: {e}") from e


@router.delete("/{name}")
async def delete_config(name: str):
    target = Path("configs") / Path(name).name
    if not target.exists():
        raise HTTPException(status_code=404, detail="Config not found")
    try:
        target.unlink()
        return {"name": target.name, "status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete config: {e}") from e
