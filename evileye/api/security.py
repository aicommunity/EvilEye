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
            "role": str(item.get("role") or "viewer"),
            "disabled": bool(item.get("disabled", False)),
            "password": item.get("password"),
            "password_hash": item.get("password_hash"),
        }
    return users


def load_web_auth_config() -> WebAuthConfig:
    creds = _load_credentials()
    section = creds.get("web_auth") if isinstance(creds, dict) else {}
    if not isinstance(section, dict):
        section = {}
    users = _normalize_users(section.get("users"))
    enabled = bool(section.get("enabled", bool(users)))
    session_secret = str(
        section.get("session_secret")
        or os.getenv("EVILEYE_SESSION_SECRET")
        or "evileye-dev-session-secret"
    )
    cookie_name = str(section.get("cookie_name") or "evileye_session")
    secure_cookies = bool(section.get("secure_cookies", False))
    internal_token = str(
        section.get("internal_token")
        or os.getenv("EVILEYE_INTERNAL_TOKEN")
        or ""
    )
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
    user = auth.users.get(username)
    if not user or user.get("disabled"):
        return None
    password_hash = user.get("password_hash")
    plain_password = user.get("password")
    if password_hash and verify_password(password, str(password_hash)):
        return user
    if plain_password is not None and hmac.compare_digest(str(plain_password), password):
        return user
    return None


def current_user(request: Request) -> Optional[dict[str, Any]]:
    user = request.session.get("user")
    if not isinstance(user, dict):
        return None
    return user


def require_authenticated(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user


def require_role(request: Request, roles: set[str]) -> dict[str, Any]:
    user = require_authenticated(request)
    role = str(user.get("role") or "viewer")
    if role not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return user


def is_api_request_protected(path: str) -> bool:
    return path.startswith("/api/v1") and not path.startswith("/api/v1/auth/")


def is_admin_request(path: str, method: str) -> bool:
    if method in {"GET", "HEAD", "OPTIONS"}:
        return False
    if path.startswith("/api/v1/internal/"):
        return False
    return path.startswith("/api/v1/")
