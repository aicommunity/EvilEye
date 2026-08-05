"""Persistent IP ban store (web_ip_bans.json)."""
from __future__ import annotations

import fcntl
import ipaddress
import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from evileye.core.logger import get_module_logger

logger = get_module_logger("api.ip_ban_store")
DEFAULT_STORE = Path("web_ip_bans.json")


def _load_store(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"bans": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"bans": []}
    if not isinstance(payload, dict):
        return {"bans": []}
    if not isinstance(payload.get("bans"), list):
        payload["bans"] = []
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
        _atomic_write(path, {"bans": []})
    with open(path, "r+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0)
            try:
                payload = json.load(handle)
            except Exception:
                payload = {"bans": []}
            if not isinstance(payload, dict):
                payload = {"bans": []}
            if not isinstance(payload.get("bans"), list):
                payload["bans"] = []
            result = callback(payload)
            handle.seek(0)
            handle.truncate(0)
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            return result
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def validate_ip_or_cidr(value: str, *, allow_cidr: bool = True) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("IP is required")
    try:
        if "/" in raw:
            if not allow_cidr:
                raise ValueError("CIDR not allowed for auto bans")
            network = ipaddress.ip_network(raw, strict=False)
            return str(network)
        return str(ipaddress.ip_address(raw))
    except ValueError as exc:
        # Allow opaque peer names (e.g. ASGI TestClient host "testclient").
        if all(c.isalnum() or c in ".-_:" for c in raw) and raw not in {".", ".."}:
            return raw
        raise ValueError(f"Invalid IP or CIDR: {value}") from exc


def _is_expired(ban: dict[str, Any], now: float | None = None) -> bool:
    expires = ban.get("expires_at")
    if expires is None:
        return False
    try:
        return float(expires) <= float(now if now is not None else time.time())
    except (TypeError, ValueError):
        return False


def _ip_matches(ban_ip: str, client_ip: str) -> bool:
    try:
        if "/" in ban_ip:
            return ipaddress.ip_address(client_ip) in ipaddress.ip_network(ban_ip, strict=False)
        return str(ipaddress.ip_address(client_ip)) == str(ipaddress.ip_address(ban_ip))
    except ValueError:
        return ban_ip == client_ip


class IpBanStore:
    def __init__(self, path: Path | None = None):
        self.path = path or DEFAULT_STORE
        self._cache_mtime: float | None = None
        self._cache_payload: dict[str, Any] | None = None

    def _load_cached(self) -> dict[str, Any]:
        path = self.path
        try:
            mtime = path.stat().st_mtime if path.exists() else -1.0
        except OSError:
            mtime = -1.0
        if self._cache_payload is not None and self._cache_mtime == mtime:
            return self._cache_payload
        payload = _load_store(path)
        self._cache_payload = payload
        self._cache_mtime = mtime
        return payload

    def _invalidate_cache(self) -> None:
        self._cache_mtime = None
        self._cache_payload = None

    def list_bans(self, *, include_expired: bool = False) -> list[dict[str, Any]]:
        payload = self._load_cached()
        now = time.time()
        items = []
        for ban in payload.get("bans") or []:
            if not isinstance(ban, dict):
                continue
            if not include_expired and _is_expired(ban, now):
                continue
            items.append(dict(ban))
        items.sort(key=lambda b: float(b.get("created_at") or 0), reverse=True)
        return items

    def find_active_ban(self, ip: str) -> Optional[dict[str, Any]]:
        now = time.time()
        for ban in self.list_bans(include_expired=False):
            if _is_expired(ban, now):
                continue
            if _ip_matches(str(ban.get("ip") or ""), ip):
                return ban
        return None

    def is_banned(self, ip: str) -> bool:
        return self.find_active_ban(ip) is not None

    def add_ban(
        self,
        ip: str,
        *,
        reason: str = "",
        source: str = "manual",
        created_by: str = "system",
        expires_at: float | None = None,
        duration_sec: float | None = None,
        notes: str = "",
        allow_cidr: bool = True,
        hit_count: int = 1,
    ) -> dict[str, Any]:
        normalized = validate_ip_or_cidr(ip, allow_cidr=allow_cidr or source == "manual")
        now = time.time()
        expiry = expires_at
        if duration_sec is not None and expiry is None:
            expiry = now + float(duration_sec)

        def mutate(payload: dict[str, Any]) -> dict[str, Any]:
            bans = payload["bans"]
            for existing in bans:
                if not isinstance(existing, dict):
                    continue
                if str(existing.get("ip")) == normalized and not _is_expired(existing, now):
                    existing["reason"] = reason or existing.get("reason") or ""
                    existing["notes"] = notes if notes else existing.get("notes") or ""
                    existing["source"] = source
                    existing["created_by"] = created_by
                    existing["expires_at"] = expiry
                    existing["hit_count"] = int(existing.get("hit_count") or 0) + int(hit_count)
                    existing["last_hit_at"] = now
                    return existing
            record = {
                "id": uuid.uuid4().hex,
                "ip": normalized,
                "reason": reason or "",
                "source": source,
                "created_at": now,
                "expires_at": expiry,
                "created_by": created_by,
                "hit_count": int(hit_count),
                "last_hit_at": now,
                "notes": notes or "",
            }
            bans.append(record)
            return record

        record = _with_lock(self.path, mutate)
        self._invalidate_cache()
        logger.warning(
            "ip_ban %s ip=%s reason=%s ttl=%s",
            source,
            normalized,
            reason,
            "permanent" if expiry is None else int(expiry - now),
        )
        return record

    def remove_ban(self, ip: str) -> bool:
        try:
            normalized = validate_ip_or_cidr(ip, allow_cidr=True)
        except ValueError:
            normalized = str(ip or "").strip()

        def mutate(payload: dict[str, Any]) -> bool:
            before = len(payload["bans"])
            payload["bans"] = [
                b for b in payload["bans"] if not (isinstance(b, dict) and str(b.get("ip")) == normalized)
            ]
            return len(payload["bans"]) < before

        removed = bool(_with_lock(self.path, mutate))
        if removed:
            self._invalidate_cache()
        return removed

    def prune_expired(self) -> int:
        now = time.time()

        def mutate(payload: dict[str, Any]) -> int:
            before = len(payload["bans"])
            payload["bans"] = [
                b for b in payload["bans"] if isinstance(b, dict) and not _is_expired(b, now)
            ]
            return before - len(payload["bans"])

        removed = int(_with_lock(self.path, mutate))
        if removed:
            self._invalidate_cache()
        return removed


_STORE: IpBanStore | None = None


def get_ip_ban_store() -> IpBanStore:
    global _STORE
    if _STORE is None:
        _STORE = IpBanStore()
    return _STORE


def reset_ip_ban_store_for_tests(path: Path | None = None) -> IpBanStore:
    global _STORE
    _STORE = IpBanStore(path)
    return _STORE
