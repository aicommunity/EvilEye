from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from evileye.api.core.camera_access import catalog_source_names, lookup_user_record, resolve_camera_access
from evileye.api.core.user_prefs import (
    allowed_cameras_from_record,
    normalize_allowed_cameras,
    prefs_from_record,
)
from evileye.api.core.web_auth_bootstrap import user_must_change_password
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


class PrefsPayload(BaseModel):
    visible_cameras: Optional[list[str]] = None
    lang: Optional[Literal["ru", "en"]] = None
    date_format: Optional[Literal["DD-MM-YYYY", "YYYY-MM-DD", "MM-DD-YYYY"]] = None


def _must_change_for_username(username: str) -> bool:
    from evileye.api.core.credentials_users import get_credentials_user, list_credentials_users
    from evileye.api.core.user_store import get_user_store

    cred = get_credentials_user(username)
    if cred is None:
        for item in list_credentials_users():
            if str(item.get("username") or "").lower() == username.lower():
                cred = item
                break
    if cred is not None:
        return user_must_change_password(cred)
    record = get_user_store().get_user_record(username)
    return user_must_change_password(record)


def _me_camera_fields(request: Request, username: str, role: str) -> dict[str, Any]:
    record = lookup_user_record(username) if username else None
    prefs = prefs_from_record(record)
    access = resolve_camera_access(request)
    if access.unrestricted or role == "admin":
        allowed = catalog_source_names(scope="active")
        camera_access = "all"
    else:
        allowed = allowed_cameras_from_record(record)
        camera_access = "restricted"
    return {
        "allowed_cameras": allowed,
        "camera_access": camera_access,
        "prefs": prefs,
    }


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
        return {
            "authenticated": True,
            "auth_enabled": False,
            "user": None,
            "permissions": [],
            "must_change_password": False,
            "allowed_cameras": catalog_source_names(scope="active"),
            "camera_access": "all",
            "prefs": prefs_from_record(None),
        }
    user = request.session.get("user")
    if not isinstance(user, dict):
        raise HTTPException(status_code=401, detail="Authentication required")
    role = normalize_role(str(user.get("role") or "user"))
    username = str(user.get("username") or "")
    session_user = {"username": username, "role": role}
    camera_fields = _me_camera_fields(request, username, role)
    return {
        "authenticated": True,
        "auth_enabled": True,
        "user": session_user,
        "permissions": permissions_for_role(role),
        "must_change_password": _must_change_for_username(username),
        **camera_fields,
    }


@router.put("/prefs")
async def auth_put_prefs(payload: PrefsPayload, request: Request) -> dict:
    from evileye.api.core.credentials_users import (
        get_credentials_user,
        list_credentials_users,
        update_credentials_user,
    )
    from evileye.api.core.user_store import get_user_store

    user = require_authenticated(request)
    username = str(user.get("username") or "").strip()
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")

    role = normalize_role(str(user.get("role") or "user"))
    record = lookup_user_record(username)
    if record is None:
        raise HTTPException(status_code=404, detail="User not found")

    patch: dict[str, Any] = {}
    raw = payload.model_dump(exclude_unset=True)
    if "visible_cameras" in raw:
        vis = raw.get("visible_cameras")
        if vis is None:
            patch["visible_cameras"] = None
        else:
            cleaned = normalize_allowed_cameras(vis)
            if role != "admin":
                allowed = set(allowed_cameras_from_record(record))
                cleaned = [n for n in cleaned if n in allowed]
            patch["visible_cameras"] = cleaned
    if "lang" in raw:
        patch["lang"] = raw.get("lang")
    if "date_format" in raw:
        patch["date_format"] = raw.get("date_format")
    if not patch:
        raise HTTPException(status_code=400, detail="At least one prefs field is required")

    cred = get_credentials_user(username)
    if cred is None:
        for item in list_credentials_users():
            if str(item.get("username") or "").lower() == username.lower():
                cred = item
                username = str(item.get("username"))
                break

    try:
        if cred is not None:
            updated = update_credentials_user(username, prefs=patch)
        else:
            updated = get_user_store().update_user(username, prefs=patch)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "ok": True,
        "prefs": prefs_from_record(updated),
        **_me_camera_fields(request, username, role),
    }


@router.post("/login")
async def auth_login(payload: LoginPayload, request: Request) -> dict:
    from evileye.api.core.rate_guard import get_rate_guard

    auth = request.app.state.web_auth
    if not auth.enabled:
        return {
            "authenticated": True,
            "auth_enabled": False,
            "user": None,
            "permissions": [],
            "must_change_password": False,
            "allowed_cameras": catalog_source_names(scope="active"),
            "camera_access": "all",
            "prefs": prefs_from_record(None),
        }
    user = authenticate_user(payload.username, payload.password, auth)
    if user is None:
        get_rate_guard().record_login_failure(request)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    get_rate_guard().record_login_success(request)
    role = normalize_role(str(user.get("role") or "user"))
    username = str(user["username"])
    session_user = {"username": username, "role": role}
    request.session["user"] = session_user
    camera_fields = _me_camera_fields(request, username, role)
    return {
        "authenticated": True,
        "auth_enabled": True,
        "user": session_user,
        "permissions": permissions_for_role(role),
        "must_change_password": _must_change_for_username(username),
        **camera_fields,
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
    return {"ok": True, "must_change_password": False}
