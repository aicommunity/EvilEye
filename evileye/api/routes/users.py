from fastapi import APIRouter, HTTPException, Request

from evileye.api.core.user_store import get_user_store
from evileye.api.security import require_permission

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("")
async def list_users(request: Request) -> dict:
    require_permission(request, "users:manage")
    items = []
    for record in get_user_store().list_users():
        items.append(
            {
                "email": record.get("email"),
                "role": record.get("role"),
                "status": record.get("status"),
                "created_at": record.get("created_at"),
            }
        )
    return {"items": items}


@router.post("/{email}/approve")
async def approve_user(email: str, request: Request) -> dict:
    require_permission(request, "users:manage")
    try:
        item = get_user_store().approve(email)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc
    return {"ok": True, "user": item}


@router.post("/{email}/reject")
async def reject_user(email: str, request: Request) -> dict:
    require_permission(request, "users:manage")
    try:
        item = get_user_store().reject(email)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc
    return {"ok": True, "user": item}
