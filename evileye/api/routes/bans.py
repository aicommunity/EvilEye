"""Admin IP ban management API."""
from __future__ import annotations

from typing import Optional
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from evileye.api.core.ip_ban_store import get_ip_ban_store, validate_ip_or_cidr
from evileye.api.core.rate_guard import get_rate_guard
from evileye.api.security import current_user, require_permission

router = APIRouter(prefix="/api/v1/bans", tags=["bans"])


class BanCreatePayload(BaseModel):
    ip: str = Field(..., min_length=1)
    reason: str = Field(default="manual")
    notes: str = Field(default="")
    expires_at: Optional[float] = None
    duration_sec: Optional[float] = None


@router.get("/protection")
async def bans_protection(request: Request) -> dict:
    require_permission(request, "bans:manage")
    return {"protection": get_rate_guard().config.public_snapshot()}


@router.get("")
async def list_bans(request: Request, include_expired: bool = Query(False)) -> dict:
    require_permission(request, "bans:manage")
    return {"items": get_ip_ban_store().list_bans(include_expired=include_expired)}


@router.post("")
async def create_ban(payload: BanCreatePayload, request: Request) -> dict:
    require_permission(request, "bans:manage")
    try:
        validate_ip_or_cidr(payload.ip, allow_cidr=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user = current_user(request) or {}
    item = get_ip_ban_store().add_ban(
        payload.ip,
        reason=payload.reason or "manual",
        source="manual",
        created_by=str(user.get("username") or "admin"),
        expires_at=payload.expires_at,
        duration_sec=payload.duration_sec,
        notes=payload.notes or "",
        allow_cidr=True,
    )
    return {"ok": True, "ban": item}


@router.delete("/{ip:path}")
async def delete_ban(ip: str, request: Request) -> dict:
    require_permission(request, "bans:manage")
    decoded = unquote(ip)
    removed = get_ip_ban_store().remove_ban(decoded)
    if not removed:
        raise HTTPException(status_code=404, detail="Ban not found")
    return {"ok": True, "ip": decoded}


@router.post("/prune")
async def prune_bans(request: Request) -> dict:
    require_permission(request, "bans:manage")
    removed = get_ip_ban_store().prune_expired()
    return {"ok": True, "removed": removed}
