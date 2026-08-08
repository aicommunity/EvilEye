from __future__ import annotations

from typing import Any, Literal, Optional
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from evileye.api.core.credentials_users import (
    count_active_admins,
    delete_credentials_user,
    get_credentials_user,
    list_credentials_users,
    update_credentials_user,
)
from evileye.api.core.user_store import get_user_store
from evileye.api.security import load_web_auth_config, normalize_role, require_permission

router = APIRouter(prefix="/api/v1/users", tags=["users"])


class CreateUserPayload(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)
    role: str = Field(default="user")


class PatchUserPayload(BaseModel):
    role: Optional[Literal["user", "admin"]] = None
    disabled: Optional[bool] = None
    status: Optional[Literal["pending", "approved", "rejected", "disabled"]] = None
    password: Optional[str] = Field(default=None, min_length=8)


def _reload_web_auth(request: Request) -> None:
    request.app.state.web_auth = load_web_auth_config()


def _public_credentials_user(record: dict[str, Any]) -> dict[str, Any]:
    username = str(record.get("username") or "")
    disabled = bool(record.get("disabled", False))
    return {
        "id": username,
        "username": username,
        "email": None,
        "role": normalize_role(str(record.get("role") or "user")),
        "status": "disabled" if disabled else "approved",
        "source": "credentials",
        "disabled": disabled,
        "created_at": None,
    }


def _public_store_user(record: dict[str, Any]) -> dict[str, Any]:
    email = str(record.get("email") or "")
    disabled = bool(record.get("disabled", False))
    status = str(record.get("status") or "pending")
    if disabled and status != "disabled":
        status = "disabled"
    return {
        "id": email,
        "username": email,
        "email": email,
        "role": normalize_role(str(record.get("role") or "user")),
        "status": status,
        "source": "store",
        "disabled": disabled,
        "created_at": record.get("created_at"),
    }


def _merged_public_users() -> list[dict[str, Any]]:
    creds = list_credentials_users()
    store = get_user_store().list_users()
    by_id: dict[str, dict[str, Any]] = {}
    for record in store:
        pub = _public_store_user(record)
        by_id[pub["id"]] = pub
    for record in creds:
        pub = _public_credentials_user(record)
        # credentials wins on id collision
        by_id[pub["id"]] = pub
    items = list(by_id.values())
    items.sort(key=lambda u: (0 if u.get("role") == "admin" else 1, str(u.get("username") or "").lower()))
    return items


def _resolve_user(user_id: str) -> tuple[Literal["credentials", "store"], dict[str, Any]]:
    raw = unquote(user_id).strip()
    if not raw:
        raise HTTPException(status_code=404, detail="User not found")
    cred = get_credentials_user(raw)
    if cred is not None:
        return "credentials", cred
    store = get_user_store().get_user_record(raw)
    if store is not None:
        return "store", store
    # try case-insensitive credentials match
    for item in list_credentials_users():
        if str(item.get("username") or "").lower() == raw.lower():
            return "credentials", item
    raise HTTPException(status_code=404, detail="User not found")


def _is_active_admin_record(source: str, record: dict[str, Any]) -> bool:
    role = normalize_role(str(record.get("role") or "user"))
    if role != "admin":
        return False
    if source == "credentials":
        return not bool(record.get("disabled", False))
    status = str(record.get("status") or "")
    return status == "approved" and not bool(record.get("disabled", False))


def _guard_last_admin(
    *,
    source: str,
    record: dict[str, Any],
    would_remove_admin: bool,
) -> None:
    if not would_remove_admin:
        return
    if not _is_active_admin_record(source, record):
        return
    if count_active_admins(list_credentials_users(), get_user_store().list_users()) <= 1:
        raise HTTPException(status_code=400, detail="Cannot remove or demote the last admin")


@router.get("")
async def list_users(request: Request) -> dict:
    require_permission(request, "users:manage")
    return {"items": _merged_public_users()}


@router.post("")
async def create_user(payload: CreateUserPayload, request: Request) -> dict:
    require_permission(request, "users:manage")
    role = normalize_role(payload.role)
    if role not in {"user", "admin"}:
        raise HTTPException(status_code=400, detail="role must be user|admin")
    try:
        item = get_user_store().create_user(payload.email, payload.password, role=role)
    except ValueError as exc:
        msg = str(exc)
        code = 409 if "already" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg) from exc
    _reload_web_auth(request)
    return {
        "ok": True,
        "user": _public_store_user(item),
        "mail": {"sent": False, "reason": "smtp_not_configured"},
    }


@router.patch("/{user_id:path}")
async def patch_user(user_id: str, payload: PatchUserPayload, request: Request) -> dict:
    actor = require_permission(request, "users:manage")
    if payload.role is None and payload.disabled is None and payload.status is None and payload.password is None:
        raise HTTPException(status_code=400, detail="At least one field is required")

    source, record = _resolve_user(user_id)
    actor_name = str(actor.get("username") or "")
    target_id = str(record.get("username") if source == "credentials" else record.get("email") or "")

    if payload.disabled is True and actor_name == target_id:
        raise HTTPException(status_code=400, detail="Cannot disable yourself")

    would_demote = False
    if payload.role is not None and normalize_role(payload.role) != "admin":
        would_demote = True
    if payload.disabled is True:
        would_demote = True
    if payload.status in {"rejected", "disabled"}:
        would_demote = True
    _guard_last_admin(source=source, record=record, would_remove_admin=would_demote)

    try:
        if source == "credentials":
            updated = update_credentials_user(
                str(record.get("username")),
                password=payload.password,
                role=payload.role,
                disabled=payload.disabled if payload.disabled is not None else (
                    True if payload.status == "disabled" else False if payload.status == "approved" else None
                ),
            )
            public = _public_credentials_user(updated)
        else:
            store = get_user_store()
            email = str(record.get("email"))
            if payload.password is not None:
                store.set_password(email, payload.password)
            updated = store.update_user(
                email,
                role=payload.role,
                status=payload.status,
                disabled=payload.disabled,
            )
            # reload after password-only change
            if payload.password is not None and payload.role is None and payload.status is None and payload.disabled is None:
                updated = store.get_user_record(email) or updated
            public = _public_store_user(updated)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc

    _reload_web_auth(request)
    return {"ok": True, "user": public}


@router.delete("/{user_id:path}")
async def delete_user(user_id: str, request: Request) -> dict:
    actor = require_permission(request, "users:manage")
    source, record = _resolve_user(user_id)
    actor_name = str(actor.get("username") or "")
    target_id = str(record.get("username") if source == "credentials" else record.get("email") or "")
    if actor_name == target_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    _guard_last_admin(source=source, record=record, would_remove_admin=True)
    try:
        if source == "credentials":
            delete_credentials_user(str(record.get("username")))
        else:
            get_user_store().delete_user(str(record.get("email")))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc
    _reload_web_auth(request)
    return {"ok": True}


@router.post("/{email}/approve")
async def approve_user(email: str, request: Request) -> dict:
    require_permission(request, "users:manage")
    try:
        item = get_user_store().approve(email)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc
    _reload_web_auth(request)
    return {"ok": True, "user": _public_store_user(item)}


@router.post("/{email}/reject")
async def reject_user(email: str, request: Request) -> dict:
    require_permission(request, "users:manage")
    try:
        item = get_user_store().reject(email)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc
    _reload_web_auth(request)
    return {"ok": True, "user": _public_store_user(item)}
