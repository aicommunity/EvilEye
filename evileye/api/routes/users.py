from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from evileye.api.core.user_store import get_user_store
from evileye.api.security import load_web_auth_config, normalize_role, require_permission

router = APIRouter(prefix="/api/v1/users", tags=["users"])


class CreateUserPayload(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=10)
    role: str = Field(default="user")


def _public_user(record: dict) -> dict:
    return {
        "email": record.get("email"),
        "role": record.get("role"),
        "status": record.get("status"),
        "created_at": record.get("created_at"),
    }


def _reload_web_auth(request: Request) -> None:
    request.app.state.web_auth = load_web_auth_config()


@router.get("")
async def list_users(request: Request) -> dict:
    require_permission(request, "users:manage")
    items = [_public_user(record) for record in get_user_store().list_users()]
    return {"items": items}


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
        "user": _public_user(item),
        "mail": {"sent": False, "reason": "smtp_not_configured"},
    }


@router.post("/{email}/approve")
async def approve_user(email: str, request: Request) -> dict:
    require_permission(request, "users:manage")
    try:
        item = get_user_store().approve(email)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc
    _reload_web_auth(request)
    return {"ok": True, "user": _public_user(item)}


@router.post("/{email}/reject")
async def reject_user(email: str, request: Request) -> dict:
    require_permission(request, "users:manage")
    try:
        item = get_user_store().reject(email)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc
    _reload_web_auth(request)
    return {"ok": True, "user": _public_user(item)}
