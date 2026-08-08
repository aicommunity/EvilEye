from __future__ import annotations

import json
import os
import secrets
import tempfile
from pathlib import Path
from typing import Any

from evileye.api.security import hash_password
from evileye.core.logger import get_module_logger

logger = get_module_logger("api.web_auth_bootstrap")

DEFAULT_ADMIN_USER = "admin"
INSECURE_SESSION_SECRETS = frozenset({"", "evileye-dev-session-secret", "change-me"})
INSECURE_PLAINTEXT_PASSWORDS = frozenset({"", "change-me", "admin", "password"})


def user_must_change_password(user_record: dict[str, Any] | None) -> bool:
    """Resolve whether the user must change password before using the UI."""
    if not isinstance(user_record, dict):
        return False
    if "must_change_password" in user_record:
        return bool(user_record.get("must_change_password"))
    # Legacy / manually edited users without the flag are not forced.
    plain = user_record.get("password")
    if isinstance(plain, str) and plain in INSECURE_PLAINTEXT_PASSWORDS:
        return True
    return False


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


def _ensure_web_auth_section(creds: dict[str, Any]) -> dict[str, Any]:
    web_auth = creds.get("web_auth")
    if not isinstance(web_auth, dict):
        web_auth = {}
        creds["web_auth"] = web_auth
    return web_auth


def ensure_secure_web_auth_secrets(path: Path | None = None) -> bool:
    """Replace weak/missing session_secret and internal_token; persist if changed."""
    creds_path = path or Path("credentials.json")
    creds = _load_json(creds_path)
    web_auth = _ensure_web_auth_section(creds)
    changed = False

    env_secret = (os.getenv("EVILEYE_SESSION_SECRET") or "").strip()
    current_secret = str(web_auth.get("session_secret") or env_secret or "").strip()
    if not current_secret or current_secret in INSECURE_SESSION_SECRETS:
        new_secret = env_secret if env_secret and env_secret not in INSECURE_SESSION_SECRETS else secrets.token_urlsafe(32)
        web_auth["session_secret"] = new_secret
        changed = True
        logger.warning("Generated secure web_auth.session_secret in %s", creds_path)

    env_token = (os.getenv("EVILEYE_INTERNAL_TOKEN") or "").strip()
    current_token = str(web_auth.get("internal_token") or env_token or "").strip()
    enabled = bool(web_auth.get("enabled", bool(web_auth.get("users"))))
    if enabled and not current_token:
        new_token = env_token or secrets.token_urlsafe(32)
        web_auth["internal_token"] = new_token
        changed = True
        logger.warning("Generated web_auth.internal_token in %s (required when auth is enabled)", creds_path)
    elif env_token and not web_auth.get("internal_token"):
        web_auth["internal_token"] = env_token
        changed = True

    if changed:
        _atomic_write(creds_path, creds)
    return changed


def ensure_default_admin_credentials(path: Path | None = None) -> bool:
    """Create default admin user in credentials.json if web_auth.users is empty."""
    creds_path = path or Path("credentials.json")
    creds = _load_json(creds_path)
    web_auth = _ensure_web_auth_section(creds)

    ensure_secure_web_auth_secrets(creds_path)
    creds = _load_json(creds_path)
    web_auth = _ensure_web_auth_section(creds)

    users = web_auth.get("users")
    if isinstance(users, list) and users:
        return False

    bootstrap_password = (os.getenv("EVILEYE_BOOTSTRAP_ADMIN_PASSWORD") or "").strip()
    if not bootstrap_password:
        bootstrap_password = secrets.token_urlsafe(12)

    password_hash = hash_password(bootstrap_password)
    web_auth["enabled"] = True
    if not str(web_auth.get("session_secret") or "").strip() or str(web_auth.get("session_secret")) in INSECURE_SESSION_SECRETS:
        web_auth["session_secret"] = os.getenv("EVILEYE_SESSION_SECRET") or secrets.token_urlsafe(32)
    if not str(web_auth.get("internal_token") or "").strip():
        web_auth["internal_token"] = os.getenv("EVILEYE_INTERNAL_TOKEN") or secrets.token_urlsafe(32)
    web_auth["users"] = [
        {
            "username": DEFAULT_ADMIN_USER,
            "password_hash": password_hash,
            "role": "admin",
            "disabled": False,
            "must_change_password": True,
        }
    ]
    _atomic_write(creds_path, creds)
    logger.warning(
        "Created default web admin credentials in %s (username=%s password=%s). "
        "Change the password immediately; this password is shown only once.",
        creds_path,
        DEFAULT_ADMIN_USER,
        bootstrap_password,
    )
    return True
