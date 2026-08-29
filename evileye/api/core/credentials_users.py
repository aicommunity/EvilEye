from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from evileye.api.core.user_prefs import merge_prefs, normalize_allowed_cameras
from evileye.api.security import hash_password, normalize_role
from evileye.core.paths import creds_path


def _default_creds() -> Path:
    return creds_path()


DEFAULT_CREDS = Path("credentials.json")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _ensure_web_auth(creds: dict[str, Any]) -> dict[str, Any]:
    web_auth = creds.get("web_auth")
    if not isinstance(web_auth, dict):
        web_auth = {}
        creds["web_auth"] = web_auth
    users = web_auth.get("users")
    if not isinstance(users, list):
        web_auth["users"] = []
    return web_auth


def _find_user_index(users: list[dict[str, Any]], username: str) -> int:
    for idx, item in enumerate(users):
        if str(item.get("username") or "") == username:
            return idx
    return -1


def list_credentials_users(path: Path | None = None) -> list[dict[str, Any]]:
    creds_path = path or _default_creds()
    web_auth = _ensure_web_auth(_load_json(creds_path))
    result: list[dict[str, Any]] = []
    for item in web_auth.get("users") or []:
        if not isinstance(item, dict):
            continue
        username = str(item.get("username") or "").strip()
        if not username:
            continue
        result.append(dict(item))
    return result


def get_credentials_user(username: str, path: Path | None = None) -> Optional[dict[str, Any]]:
    target = str(username or "")
    for item in list_credentials_users(path):
        if str(item.get("username") or "") == target:
            return item
    return None


def update_credentials_user(
    username: str,
    *,
    password: str | None = None,
    role: str | None = None,
    disabled: bool | None = None,
    allowed_cameras: list[str] | None = None,
    prefs: dict[str, Any] | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    creds_path = path or _default_creds()
    creds = _load_json(creds_path)
    web_auth = _ensure_web_auth(creds)
    users: list[dict[str, Any]] = list(web_auth.get("users") or [])
    idx = _find_user_index(users, username)
    if idx < 0:
        raise KeyError("User not found")
    item = dict(users[idx])
    if password is not None:
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters")
        item["password_hash"] = hash_password(password)
        item.pop("password", None)
        item["must_change_password"] = False
    if role is not None:
        item["role"] = normalize_role(role)
    if disabled is not None:
        item["disabled"] = bool(disabled)
    if allowed_cameras is not None:
        item["allowed_cameras"] = normalize_allowed_cameras(allowed_cameras)
    if prefs is not None:
        item["prefs"] = merge_prefs(item.get("prefs"), prefs)
    users[idx] = item
    web_auth["users"] = users
    _atomic_write(creds_path, creds)
    return item


def set_credentials_password(username: str, new_password: str, path: Path | None = None) -> dict[str, Any]:
    return update_credentials_user(username, password=new_password, path=path)


def delete_credentials_user(username: str, path: Path | None = None) -> None:
    creds_path = path or _default_creds()
    creds = _load_json(creds_path)
    web_auth = _ensure_web_auth(creds)
    users: list[dict[str, Any]] = list(web_auth.get("users") or [])
    idx = _find_user_index(users, username)
    if idx < 0:
        raise KeyError("User not found")
    users.pop(idx)
    web_auth["users"] = users
    _atomic_write(creds_path, creds)


def count_active_admins(
    creds_users: list[dict[str, Any]] | None = None,
    store_users: list[dict[str, Any]] | None = None,
) -> int:
    count = 0
    for item in creds_users or []:
        role = normalize_role(str(item.get("role") or "user"))
        if role == "admin" and not bool(item.get("disabled", False)):
            count += 1
    for item in store_users or []:
        role = normalize_role(str(item.get("role") or "user"))
        status = str(item.get("status") or "")
        disabled = bool(item.get("disabled", False))
        if role == "admin" and status == "approved" and not disabled:
            count += 1
    return count
