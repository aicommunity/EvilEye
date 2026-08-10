"""System-level control endpoints (restart pipeline safely)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from evileye.api.core.config_run_access import get_config_run_manager
from evileye.api.core.public_base_url import resolve_public_api_base_url
from evileye.api.core.safe_paths import UnsafePathError

router = APIRouter(prefix="/api/v1/system", tags=["system"])


class SystemRestartPayload(BaseModel):
    config_name: Optional[str] = Field(
        None,
        description="Config file name (e.g. poly-cameras-gst.json). Defaults to current running config.",
    )


@router.post("/restart")
async def system_restart(payload: SystemRestartPayload | None = None) -> dict:
    """
    Restart the surveillance pipeline for a config without killing the API mid-request
    when the API is embedded in that pipeline (evileye run).
    """
    body = payload or SystemRestartPayload()
    name = (body.config_name or "").strip()
    if not name:
        # Fall back to any current running config from registry
        from evileye.api.core.runtime_registry import list_runtime_records

        records = list_runtime_records()
        running = [
            r
            for r in records.values()
            if isinstance(r, dict)
            and (r.get("alive") or r.get("state") in {"running", "starting"})
            and r.get("config_path")
        ]
        if not running:
            raise HTTPException(status_code=400, detail="config_name is required (no running config found)")
        from pathlib import Path

        name = Path(str(running[0]["config_path"])).name

    try:
        api_base = resolve_public_api_base_url()
        return get_config_run_manager().restart_for_config(name, api_base_url=api_base)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Config file not found") from exc
    except (ValueError, UnsafePathError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
