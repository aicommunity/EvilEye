from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from pathlib import Path
import json

""" Module for managing configuration files via the API"""

router = APIRouter(prefix="/api/v1/configs", tags=["configs"])


class ConfigUpsert(BaseModel):
    name: str = Field(..., description="The name of the configuration file, for example single_video.json")
    body: dict = Field(..., description="JSON configuration content")


# Model for opening (running) a config
class ConfigRunCreate(BaseModel):
    name: Optional[str] = Field(None, description="Human-readable name (auto-generated if not provided)")
    config_name: Optional[str] = Field(None, description="Configuration name from the configs folder")
    config_body: Optional[dict] = Field(None, description="Configuration body, if file name not used")


@router.get("/list")
async def list_configs() -> List[str]:
    configs_dir = Path("configs")
    if not configs_dir.exists():
        return []
    return sorted([p.name for p in configs_dir.glob("*.json")])


@router.get("/{name}")
# Passing the file name to the url is not very good practice
async def get_config(name: str) -> dict:
    path = Path("configs") / name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Config not found")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read config: {e}")


# create config file
@router.post("/create")
async def create_config(payload: ConfigUpsert):
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
        raise HTTPException(status_code=500, detail=f"Failed to create config: {e}")


@router.put("/update")
# Passing the file name to the uri is not very good practice
async def update_config(payload: ConfigUpsert):
    name_config = payload.name
    target = Path("configs") / Path(name_config).name
    if not target.exists():
        raise HTTPException(status_code=404, detail="Config not found")
    try:
        with open(target, "w", encoding="utf-8") as f:
            json.dump(payload.body, f, ensure_ascii=False, indent=2)
        return {"name": target.name, "status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update config: {e}")


# Open config to run (create run) — placed after Update for docs order
@router.post("/open", summary="Open Config to run")
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
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Config file not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{name}")
# Passing the file name to the uri is not very good practice
async def delete_config(name: str):
    target = Path("configs") / Path(name).name
    if not target.exists():
        raise HTTPException(status_code=404, detail="Config not found")
    try:
        target.unlink()
        return {"name": target.name, "status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete config: {e}")

from evileye.api.core.config_run_access import get_config_run_manager


@router.get("/runs/list")
async def list_config_runs() -> Dict[int, Dict]:
    return get_config_run_manager().list()


 


@router.get("/runs/{rid}/status")
async def get_config_run(rid: int) -> Dict:
    try:
        return get_config_run_manager().describe(rid)
    except KeyError:
        raise HTTPException(status_code=404, detail="Config run not found")


@router.post("/runs/{rid}/start")
async def start_config_run(rid: int) -> Dict:
    try:
        return get_config_run_manager().start(rid)
    except KeyError:
        raise HTTPException(status_code=404, detail="Config run not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runs/{rid}/stop")
async def stop_config_run(rid: int) -> Dict:
    try:
        return get_config_run_manager().stop(rid)
    except KeyError:
        raise HTTPException(status_code=404, detail="Config run not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/runs/{rid}/delete")
async def delete_config_run(rid: int) -> Dict:
    try:
        return get_config_run_manager().delete(rid)
    except KeyError:
        raise HTTPException(status_code=404, detail="Config run not found")
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
