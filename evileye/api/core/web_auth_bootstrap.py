from __future__ import annotations

import json
import os
import secrets
import tempfile
from pathlib import Path
from typing import Any

from evileye.api.security import hash_password
from evileye.core.logger import get_module_logger
from evileye.core.paths import creds_path

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


BOOTSTRAP_PASSWORD_FILE_NAME = "web_admin_bootstrap_password.txt"


def bootstrap_password_file_path(path: Path | None = None) -> Path:
    """Location of the one-time bootstrap admin password note (next to credentials)."""
    creds_file = path or creds_path()
    return creds_file.parent / BOOTSTRAP_PASSWORD_FILE_NAME


def clear_bootstrap_password_file(path: Path | None = None) -> bool:
    """Remove the one-time bootstrap password note; call after the password is changed."""
    note = bootstrap_password_file_path(path)
    try:
        if note.exists():
            note.unlink()
            logger.info("Removed one-time bootstrap admin password note %s", note)
            return True
    except OSError:
        logger.warning("Failed to remove bootstrap admin password note %s", note, exc_info=True)
    return False


def _write_bootstrap_password_note(note: Path, password: str) -> None:
    """Store the generated password in a 0600 file instead of the log."""
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        f"EvilEye bootstrap admin password\nUsername: {DEFAULT_ADMIN_USER}\n"
        f"Password: {password}\n\nDelete this file or change the password immediately.\n",
        encoding="utf-8",
    )
    try:
        note.chmod(0o600)
    except OSError:
        # Windows filesystems may not fully honour POSIX modes; the file still
        # lives next to credentials.json which holds the hashes anyway.
        pass


def resolve_must_change_password(username: str) -> bool:
    """Resolve the must-change-password flag from live user stores (not the session)."""
    if not username:
        return False
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
    creds_file = path or creds_path()
    creds = _load_json(creds_file)
    web_auth = _ensure_web_auth_section(creds)
    changed = False

    env_secret = (os.getenv("EVILEYE_SESSION_SECRET") or "").strip()
    current_secret = str(web_auth.get("session_secret") or env_secret or "").strip()
    if not current_secret or current_secret in INSECURE_SESSION_SECRETS:
        new_secret = env_secret if env_secret and env_secret not in INSECURE_SESSION_SECRETS else secrets.token_urlsafe(32)
        web_auth["session_secret"] = new_secret
        changed = True
        logger.warning("Generated secure web_auth.session_secret in %s", creds_file)

    env_token = (os.getenv("EVILEYE_INTERNAL_TOKEN") or "").strip()
    current_token = str(web_auth.get("internal_token") or env_token or "").strip()
    enabled = bool(web_auth.get("enabled", bool(web_auth.get("users"))))
    if enabled and not current_token:
        new_token = env_token or secrets.token_urlsafe(32)
        web_auth["internal_token"] = new_token
        changed = True
        logger.warning("Generated web_auth.internal_token in %s (required when auth is enabled)", creds_file)
    elif env_token and not web_auth.get("internal_token"):
        web_auth["internal_token"] = env_token
        changed = True

    if changed:
        _atomic_write(creds_file, creds)
    return changed


def ensure_default_admin_credentials(path: Path | None = None) -> bool:
    """Create default admin user in credentials.json if web_auth.users is empty."""
    creds_file = path or creds_path()
    creds = _load_json(creds_file)
    web_auth = _ensure_web_auth_section(creds)

    ensure_secure_web_auth_secrets(creds_file)
    creds = _load_json(creds_file)
    web_auth = _ensure_web_auth_section(creds)

    users = web_auth.get("users")
    if isinstance(users, list) and users:
        return False

    env_provided_password = (os.getenv("EVILEYE_BOOTSTRAP_ADMIN_PASSWORD") or "").strip()
    bootstrap_password = env_provided_password or secrets.token_urlsafe(12)

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
    _atomic_write(creds_file, creds)
    # Never log the password itself: log files are copied into incident reports
    # and kept forever. A random password is stored once in a 0600 note next to
    # the credentials file and removed after the first password change; a
    # password supplied via EVILEYE_BOOTSTRAP_ADMIN_PASSWORD is not echoed at all.
    if env_provided_password:
        logger.warning(
            "Created default web admin user %r in %s with the password from "
            "EVILEYE_BOOTSTRAP_ADMIN_PASSWORD. Change the password after first login.",
            DEFAULT_ADMIN_USER,
            creds_file,
        )
    else:
        try:
            _write_bootstrap_password_note(bootstrap_password_file_path(creds_file), bootstrap_password)
        except OSError:
            logger.error(
                "Created default web admin user %r in %s but failed to write the "
                "one-time password note; use EVILEYE_BOOTSTRAP_ADMIN_PASSWORD to reset.",
                DEFAULT_ADMIN_USER,
                creds_file,
            )
            return True
        logger.warning(
            "Created default web admin credentials in %s (username=%s). The one-time "
            "password is stored in %s (0600) and is NOT logged. Change the password "
            "immediately; the note is removed automatically afterwards.",
            creds_file,
            DEFAULT_ADMIN_USER,
            bootstrap_password_file_path(creds_file),
        )
    return True
