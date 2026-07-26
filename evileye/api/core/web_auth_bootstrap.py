from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from evileye.api.security import hash_password
from evileye.core.logger import get_module_logger

logger = get_module_logger("api.web_auth_bootstrap")

DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_PASS = "admin"


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


def ensure_default_admin_credentials(path: Path | None = None) -> bool:
    """Create default admin user in credentials.json if web_auth.users is empty."""
    creds_path = path or Path("credentials.json")
    creds = _load_json(creds_path)
    web_auth = creds.get("web_auth")
    if not isinstance(web_auth, dict):
        web_auth = {}
        creds["web_auth"] = web_auth

    users = web_auth.get("users")
    if isinstance(users, list) and users:
        return False

    password_hash = hash_password(DEFAULT_ADMIN_PASS)
    web_auth["enabled"] = True
    web_auth.setdefault("session_secret", os.getenv("EVILEYE_SESSION_SECRET") or "evileye-dev-session-secret")
    web_auth["users"] = [
        {
            "username": DEFAULT_ADMIN_USER,
            "password_hash": password_hash,
            "role": "admin",
            "disabled": False,
        }
    ]
    _atomic_write(creds_path, creds)
    logger.warning(
        "Created default web admin credentials in %s (username=%s). Change the password immediately.",
        creds_path,
        DEFAULT_ADMIN_USER,
    )
    return True
