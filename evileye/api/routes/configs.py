from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List
from pathlib import Path
import json

""" Module for managing configuration files via the API"""

router = APIRouter(prefix="/api/v1/configs", tags=["configs"])


class ConfigUpsert(BaseModel):
    name: str = Field(..., description="The name of the configuration file, for example single_video.json")
    body: dict = Field(..., description="JSON configuration content")


@router.get("")
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


@router.post("")
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


@router.put("")
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

