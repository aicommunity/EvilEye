"""Admin-only pipeline builder and plugin workshop API."""

from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from evileye.api.core.client_ip import resolve_client_ip
from evileye.api.core.rate_guard import load_protection_config
from evileye.api.security import require_role
from evileye.core.extension_builder import (
    PluginScaffoldError,
    create_plugin_operation,
    extension_catalog,
    get_plugin_operation,
    list_plugin_operations,
    plugin_operation_archive,
    preview_pipeline,
    save_pipeline,
)

router = APIRouter(prefix="/api/v1/admin/extensions", tags=["admin extensions"])


class PipelinePreviewRequest(BaseModel):
    config: dict[str, Any]


class PipelineSaveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    config: dict[str, Any]
    create_only: bool = True


class PluginCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    template: str = "processor"


def _localhost_only() -> bool:
    value = os.getenv("EVILEYE_BUILDER_LOCALHOST_ONLY")
    if value is None:
        return True
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _assert_builder_access(request: Request) -> None:
    require_role(request, {"admin"})
    if not _localhost_only():
        return
    try:
        from evileye.core.paths import creds_path

        credentials_path = creds_path()
        payload = json.loads(credentials_path.read_text(encoding="utf-8")) if credentials_path.is_file() else {}
        auth_section = payload.get("web_auth", {}) if isinstance(payload, dict) else {}
        config = load_protection_config(auth_section if isinstance(auth_section, dict) else {})
        address = resolve_client_ip(
            request,
            trust_proxy=config.trust_proxy,
            trusted_proxy_ips=config.trusted_proxy_ips,
        )
        if not ipaddress.ip_address(address).is_loopback:
            raise ValueError("not localhost")
    except Exception as exc:
        raise HTTPException(status_code=403, detail="This admin workspace is available from localhost only") from exc


@router.get("/catalog")
async def get_extension_catalog(request: Request) -> dict[str, Any]:
    _assert_builder_access(request)
    try:
        return extension_catalog()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extension catalog failed: {exc}") from exc


@router.post("/preview")
async def preview_pipeline_config(payload: PipelinePreviewRequest, request: Request) -> dict[str, Any]:
    _assert_builder_access(request)
    try:
        return preview_pipeline(payload.config)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/configs")
async def save_pipeline_config(payload: PipelineSaveRequest, request: Request) -> dict[str, Any]:
    _assert_builder_access(request)
    try:
        return save_pipeline(payload.name, payload.config, create_only=payload.create_only)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline configuration save failed: {exc}") from exc


@router.post("/plugins")
async def create_plugin(payload: PluginCreateRequest, request: Request) -> dict[str, Any]:
    _assert_builder_access(request)
    try:
        return create_plugin_operation(payload.name, payload.template)
    except PluginScaffoldError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Plugin creation failed: {exc}") from exc


@router.get("/operations/{operation_id}")
async def get_extension_operation(operation_id: str, request: Request) -> dict[str, Any]:
    _assert_builder_access(request)
    try:
        return get_plugin_operation(operation_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Extension operation not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/operations")
async def list_extension_operations(request: Request) -> list[dict[str, Any]]:
    _assert_builder_access(request)
    try:
        return list_plugin_operations()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extension operation history failed: {exc}") from exc


@router.get("/operations/{operation_id}/archive")
async def download_plugin_archive(operation_id: str, request: Request):
    _assert_builder_access(request)
    try:
        operation = get_plugin_operation(operation_id)
        archive = plugin_operation_archive(operation_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Plugin archive not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(
        path=archive,
        media_type="application/zip",
        filename=f"evileye-plugin-{operation.get('name', operation_id)}.zip",
    )
