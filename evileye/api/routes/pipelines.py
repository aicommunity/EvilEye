from pathlib import Path
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Optional
from evileye.api.core.manager_access import get_manager

router = APIRouter(prefix="/api/v1/pipelines", tags=["pipelines"])


class PipelineCreate(BaseModel):
    name: Optional[str] = Field(None, description="Human-readable name (auto-generated if not provided)")
    config_name: Optional[str] = Field(None, description="Configuration name from the configs folder")
    config_body: Optional[dict] = Field(None, description="The configuration body, if we do not use the file")


@router.get("")
async def list_pipelines() -> Dict[int, Dict]:
    return get_manager().list()


@router.post("/create")
async def create_pipeline(pipeline: PipelineCreate) -> Dict:
    data = pipeline.model_dump()
    # Always generate integer ID
    pid = len(get_manager().list()) + 1
    config_body = data.get("config_body")
    if config_body is None and data.get("config_name"):
        cfg_path = Path("configs") / data["config_name"]
        if not cfg_path.exists():
            raise HTTPException(status_code=404, detail="Config file not found")
        with open(cfg_path, "r", encoding="utf-8") as f:
            config_body = json.load(f)
    if config_body is None:
        raise HTTPException(status_code=400, detail="Provide config_body or config_name")
    try:
        return get_manager().create(pid, config_body, data.get("name"))
    except ValueError:
        raise HTTPException(status_code=409, detail="Pipeline already exists")


@router.get("/{pid}")
async def get_pipeline(pid: int) -> Dict:
    try:
        return get_manager().describe(pid)
    except KeyError:
        raise HTTPException(status_code=404, detail="Pipeline not found")


## start/stop endpoints removed per new API design


@router.delete("/{pid}")
async def delete_pipeline(pid: int) -> Dict:
    try:
        return get_manager().delete(pid)
    except KeyError:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


# @router.put("/{pid}")
# async def update_pipeline(pid: str, payload: PipelineCreate) -> Dict:
#     # For now only allow updating name in manager's stored config
#     try:
#         desc = get_manager().describe(pid)
#     except KeyError:
#         raise HTTPException(status_code=404, detail="Pipeline not found")
#     data = payload.model_dump()
#     # No hot-reload; just update reported name if provided
#     if data.get("name"):
#         desc["name"] = data["name"]
#     return desc


