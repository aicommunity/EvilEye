"""System-level control endpoints (restart pipeline safely)."""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from evileye.api.core.config_run_access import get_config_run_manager
from evileye.api.core.public_base_url import resolve_public_api_base_url
from evileye.api.core.safe_paths import UnsafePathError
from evileye.api.security import require_permission

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/runtime")
async def system_runtime(request: Request) -> dict:
    """Return runtime health for plugin modules and the event delivery path."""
    require_permission(request, "runtime:view")
    from evileye.api.core.control_ipc import control_socket_path, send_control_command

    if not control_socket_path().exists():
        raise HTTPException(status_code=503, detail="Runtime controller is not available")
    response = await asyncio.to_thread(
        send_control_command,
        {"cmd": "get_runtime_stats"},
        timeout=2.0,
    )
    if not isinstance(response, dict) or response.get("ok") is not True:
        error = response.get("error") if isinstance(response, dict) else "invalid_response"
        raise HTTPException(status_code=503, detail=f"Runtime diagnostics unavailable: {error}")
    stats = response.get("stats")
    if not isinstance(stats, dict):
        raise HTTPException(status_code=503, detail="Runtime diagnostics returned an invalid payload")
    return stats


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
