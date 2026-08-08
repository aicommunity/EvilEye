from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from evileye.api.security import (
    authenticate_user,
    load_web_auth_config,
    normalize_role,
    permissions_for_role,
    require_authenticated,
    verify_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginPayload(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class RegisterPayload(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)


class ChangePasswordPayload(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)


@router.post("/register")
async def auth_register(payload: RegisterPayload, request: Request) -> dict:
    from evileye.api.core.rate_guard import get_rate_guard
    from evileye.api.core.user_store import get_user_store

    if get_rate_guard().record_register(request):
        raise HTTPException(status_code=403, detail="IP banned")
    try:
        user = get_user_store().register(payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "message": "Registration submitted. Wait for administrator approval.",
        "user": {"email": user.get("email"), "status": user.get("status")},
    }


@router.get("/me")
async def auth_me(request: Request) -> dict:
    auth = request.app.state.web_auth
    if not auth.enabled:
        return {"authenticated": True, "auth_enabled": False, "user": None, "permissions": []}
    user = request.session.get("user")
    if not isinstance(user, dict):
        raise HTTPException(status_code=401, detail="Authentication required")
    role = normalize_role(str(user.get("role") or "user"))
    session_user = {"username": user.get("username"), "role": role}
    return {
        "authenticated": True,
        "auth_enabled": True,
        "user": session_user,
        "permissions": permissions_for_role(role),
    }


@router.post("/login")
async def auth_login(payload: LoginPayload, request: Request) -> dict:
    from evileye.api.core.rate_guard import get_rate_guard

    auth = request.app.state.web_auth
    if not auth.enabled:
        return {"authenticated": True, "auth_enabled": False, "user": None, "permissions": []}
    user = authenticate_user(payload.username, payload.password, auth)
    if user is None:
        get_rate_guard().record_login_failure(request)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    get_rate_guard().record_login_success(request)
    role = normalize_role(str(user.get("role") or "user"))
    session_user = {"username": user["username"], "role": role}
    request.session["user"] = session_user
    return {
        "authenticated": True,
        "auth_enabled": True,
        "user": session_user,
        "permissions": permissions_for_role(role),
    }


@router.post("/logout")
async def auth_logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@router.post("/change-password")
async def auth_change_password(payload: ChangePasswordPayload, request: Request) -> dict:
    from evileye.api.core.credentials_users import (
        get_credentials_user,
        list_credentials_users,
        set_credentials_password,
    )
    from evileye.api.core.user_store import get_user_store

    user = require_authenticated(request)
    username = str(user.get("username") or "").strip()
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")

    cred = get_credentials_user(username)
    if cred is None:
        for item in list_credentials_users():
            if str(item.get("username") or "").lower() == username.lower():
                cred = item
                username = str(item.get("username"))
                break

    if cred is not None:
        password_hash = cred.get("password_hash")
        plain = cred.get("password")
        ok = False
        if password_hash and verify_password(payload.current_password, str(password_hash)):
            ok = True
        elif plain is not None and str(plain) == payload.current_password:
            ok = True
        if not ok:
            raise HTTPException(status_code=401, detail="Invalid current password")
        try:
            set_credentials_password(username, payload.new_password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        store = get_user_store()
        record = store.get_user_record(username)
        if record is None:
            raise HTTPException(status_code=404, detail="User not found")
        password_hash = record.get("password_hash")
        if not password_hash or not verify_password(payload.current_password, str(password_hash)):
            raise HTTPException(status_code=401, detail="Invalid current password")
        try:
            store.set_password(username, payload.new_password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    request.app.state.web_auth = load_web_auth_config()
    return {"ok": True}
