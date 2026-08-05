import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException, Request, status


@dataclass
class WebAuthConfig:
    enabled: bool
    session_secret: str
    cookie_name: str
    secure_cookies: bool
    users: dict[str, dict[str, Any]]
    internal_token: str


ROLE_PERMISSIONS: dict[str, set[str]] = {
    "user": {"live:view", "journal:view"},
    "power_user": {"live:view", "journal:view", "history:view", "logs:view"},
    "admin": {
        "live:view",
        "journal:view",
        "logs:view",
        "runtime:view",
        "runtime:control",
        "history:view",
        "history:edit",
        "config:view",
        "config:edit",
        "system:admin",
        "users:manage",
        "bans:manage",
    },
    # Backward compatibility with previous naming.
    "viewer": {"live:view", "journal:view"},
}


def _load_credentials() -> dict[str, Any]:
    path = Path("credentials.json")
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _normalize_users(raw_users: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    users: dict[str, dict[str, Any]] = {}
    for item in raw_users or []:
        username = str(item.get("username") or "").strip()
        if not username:
            continue
        users[username] = {
            "username": username,
            "role": normalize_role(str(item.get("role") or "user")),
            "disabled": bool(item.get("disabled", False)),
            "password": item.get("password"),
            "password_hash": item.get("password_hash"),
        }
    return users


def normalize_role(role: str) -> str:
    value = (role or "user").strip().lower()
    if value in ROLE_PERMISSIONS:
        return value
    return "user"


def permissions_for_role(role: str) -> list[str]:
    return sorted(ROLE_PERMISSIONS.get(normalize_role(role), ROLE_PERMISSIONS["user"]))


def load_web_auth_config() -> WebAuthConfig:
    from evileye.api.core.web_auth_bootstrap import (
        ensure_default_admin_credentials,
        ensure_secure_web_auth_secrets,
    )

    ensure_default_admin_credentials()
    ensure_secure_web_auth_secrets()
    creds = _load_credentials()
    section = creds.get("web_auth") if isinstance(creds, dict) else {}
    if not isinstance(section, dict):
        section = {}
    users = _normalize_users(section.get("users"))
    try:
        from evileye.api.core.user_store import get_user_store

        for record in get_user_store().list_users():
            if record.get("status") != "approved":
                continue
            email = str(record.get("email") or "").strip()
            if not email:
                continue
            users[email] = {
                "username": email,
                "role": normalize_role(str(record.get("role") or "user")),
                "disabled": False,
                "password_hash": record.get("password_hash"),
            }
    except Exception:
        pass
    enabled = bool(section.get("enabled", bool(users)))
    session_secret = str(
        section.get("session_secret")
        or os.getenv("EVILEYE_SESSION_SECRET")
        or ""
    ).strip()
    if not session_secret:
        # Should have been persisted by ensure_secure_web_auth_secrets; last-resort ephemeral.
        import secrets as _secrets

        session_secret = _secrets.token_urlsafe(32)
    cookie_name = str(section.get("cookie_name") or "evileye_session")
    secure_cookies = bool(section.get("secure_cookies", False))
    if os.getenv("EVILEYE_SSL_CERTFILE") or os.getenv("EVILEYE_SSL_KEYFILE"):
        secure_cookies = True
    internal_token = str(
        section.get("internal_token")
        or os.getenv("EVILEYE_INTERNAL_TOKEN")
        or ""
    ).strip()
    return WebAuthConfig(
        enabled=enabled,
        session_secret=session_secret,
        cookie_name=cookie_name,
        secure_cookies=secure_cookies,
        users=users,
        internal_token=internal_token,
    )


def hash_password(password: str, *, salt: Optional[str] = None, iterations: int = 390000) -> str:
    salt_value = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_value.encode("utf-8"),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt_value}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        int(iterations),
    ).hex()
    return hmac.compare_digest(candidate, expected)


def authenticate_user(username: str, password: str, auth: WebAuthConfig) -> Optional[dict[str, Any]]:
    allow_plaintext = os.getenv("EVILEYE_ALLOW_PLAINTEXT_PASSWORDS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    user = auth.users.get(username)
    if user and not user.get("disabled"):
        password_hash = user.get("password_hash")
        plain_password = user.get("password")
        if password_hash and verify_password(password, str(password_hash)):
            return user
        if (
            allow_plaintext
            and plain_password is not None
            and isinstance(plain_password, str)
            and len(plain_password) == len(password)
            and hmac.compare_digest(plain_password, password)
        ):
            return user
    try:
        from evileye.api.core.user_store import get_user_store

        store_user = get_user_store().authenticate(username, password)
        if store_user is not None:
            return store_user
    except Exception:
        pass
    return None


def current_user(request: Request) -> Optional[dict[str, Any]]:
    user = request.session.get("user")
    if not isinstance(user, dict):
        return None
    if "role" in user:
        user["role"] = normalize_role(str(user.get("role") or "user"))
        user["permissions"] = permissions_for_role(user["role"])
    return user


def require_authenticated(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user


def require_role(request: Request, roles: set[str]) -> dict[str, Any]:
    user = require_authenticated(request)
    role = normalize_role(str(user.get("role") or "user"))
    if role not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return user


def require_permission(request: Request, permission: str) -> dict[str, Any]:
    user = require_authenticated(request)
    permissions = set(user.get("permissions") or permissions_for_role(str(user.get("role") or "user")))
    if permission not in permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return user


def is_api_request_protected(path: str) -> bool:
    return path.startswith("/api/v1") and not path.startswith("/api/v1/auth/")


def required_permissions_for_request(path: str, method: str) -> set[str]:
    if method in {"HEAD", "OPTIONS"}:
        return set()
    if path.startswith("/api/v1/internal/"):
        return set()
    if path.startswith("/api/v1/playback"):
        return {"journal:view"}
    if path.startswith("/api/v1/journals/config-history"):
        return {"history:view"} if method == "GET" else {"history:edit"}
    if path.startswith("/api/v1/journals/export"):
        return {"journal:view"}
    if path.startswith("/api/v1/logs"):
        return {"logs:view"}
    if path.startswith("/api/v1/users"):
        return {"users:manage"}
    if path.startswith("/api/v1/bans"):
        return {"bans:manage"}
    if path.startswith("/api/v1/journals/"):
        return {"journal:view"}
    if path.startswith("/api/v1/state/"):
        return {"live:view"}
    if path.startswith("/api/v1/runs/") or path.startswith("/api/v1/pipelines/"):
        return {"live:view"}
    if path.startswith("/api/v1/configs/runs"):
        return {"runtime:view"} if method == "GET" else {"runtime:control"}
    if path.startswith("/api/v1/configs"):
        return {"config:view"} if method == "GET" else {"config:edit"}
    if path.startswith("/api/v1/version"):
        return {"live:view"}
    return {"system:admin"} if method not in {"GET"} else {"live:view"}
