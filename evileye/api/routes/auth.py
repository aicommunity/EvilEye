from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from evileye.api.security import authenticate_user


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginPayload(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


@router.get("/me")
async def auth_me(request: Request) -> dict:
    auth = request.app.state.web_auth
    if not auth.enabled:
        return {"authenticated": True, "auth_enabled": False, "user": None}
    user = request.session.get("user")
    if not isinstance(user, dict):
        raise HTTPException(status_code=401, detail="Authentication required")
    return {"authenticated": True, "auth_enabled": True, "user": user}


@router.post("/login")
async def auth_login(payload: LoginPayload, request: Request) -> dict:
    auth = request.app.state.web_auth
    if not auth.enabled:
        return {"authenticated": True, "auth_enabled": False, "user": None}
    user = authenticate_user(payload.username, payload.password, auth)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    session_user = {"username": user["username"], "role": user.get("role") or "viewer"}
    request.session["user"] = session_user
    return {"authenticated": True, "auth_enabled": True, "user": session_user}


@router.post("/logout")
async def auth_logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}
