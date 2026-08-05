from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from evileye.api.security import hash_password, normalize_role, verify_password

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DEFAULT_STORE = Path("web_users.json")


def _load_store(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"users": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"users": []}
    if not isinstance(payload, dict):
        return {"users": []}
    if not isinstance(payload.get("users"), list):
        payload["users"] = []
    return payload


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


def _with_lock(path: Path, callback):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        _atomic_write(path, {"users": []})
    with open(path, "r+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0)
            try:
                payload = json.load(handle)
            except Exception:
                payload = {"users": []}
            if not isinstance(payload, dict):
                payload = {"users": []}
            if not isinstance(payload.get("users"), list):
                payload["users"] = []
            result = callback(payload)
            handle.seek(0)
            handle.truncate(0)
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            return result
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class UserStore:
    def __init__(self, path: Path | None = None):
        self.path = path or DEFAULT_STORE

    def register(self, email: str, password: str) -> dict[str, Any]:
        normalized = email.strip().lower()
        if not EMAIL_RE.match(normalized):
            raise ValueError("Invalid email address")
        if len(password) < 10:
            raise ValueError("Password must be at least 10 characters")

        def mutate(payload: dict[str, Any]) -> dict[str, Any]:
            users = payload["users"]
            for item in users:
                if str(item.get("email", "")).lower() == normalized:
                    raise ValueError("Email already registered")
            record = {
                "email": normalized,
                "password_hash": hash_password(password),
                "role": "user",
                "status": "pending",
                "created_at": time.time(),
            }
            users.append(record)
            return record

        return _with_lock(self.path, mutate)

    def create_user(self, email: str, password: str, *, role: str = "user") -> dict[str, Any]:
        """Admin-created user: immediately approved (no email invite)."""
        normalized = email.strip().lower()
        if not EMAIL_RE.match(normalized):
            raise ValueError("Invalid email address")
        if len(password) < 10:
            raise ValueError("Password must be at least 10 characters")
        resolved_role = normalize_role(role)

        def mutate(payload: dict[str, Any]) -> dict[str, Any]:
            users = payload["users"]
            for item in users:
                if str(item.get("email", "")).lower() == normalized:
                    raise ValueError("Email already registered")
            record = {
                "email": normalized,
                "password_hash": hash_password(password),
                "role": resolved_role,
                "status": "approved",
                "created_at": time.time(),
            }
            users.append(record)
            return record

        return _with_lock(self.path, mutate)

    def list_users(self) -> list[dict[str, Any]]:
        payload = _load_store(self.path)
        return list(payload.get("users") or [])

    def approve(self, email: str) -> dict[str, Any]:
        normalized = email.strip().lower()

        def mutate(payload: dict[str, Any]) -> dict[str, Any]:
            for item in payload["users"]:
                if str(item.get("email", "")).lower() == normalized:
                    item["status"] = "approved"
                    return item
            raise KeyError("User not found")

        return _with_lock(self.path, mutate)

    def reject(self, email: str) -> dict[str, Any]:
        normalized = email.strip().lower()

        def mutate(payload: dict[str, Any]) -> dict[str, Any]:
            for item in payload["users"]:
                if str(item.get("email", "")).lower() == normalized:
                    item["status"] = "rejected"
                    return item
            raise KeyError("User not found")

        return _with_lock(self.path, mutate)

    def get_user_record(self, email: str) -> Optional[dict[str, Any]]:
        normalized = email.strip().lower()
        for item in self.list_users():
            if str(item.get("email", "")).lower() == normalized:
                return item
        return None

    def authenticate(self, email: str, password: str) -> Optional[dict[str, Any]]:
        record = self.get_user_record(email)
        if not record or record.get("status") != "approved":
            return None
        password_hash = record.get("password_hash")
        if not password_hash or not verify_password(password, str(password_hash)):
            return None
        return {
            "username": record["email"],
            "role": str(record.get("role") or "user"),
            "disabled": False,
        }


def get_user_store() -> UserStore:
    return UserStore()
