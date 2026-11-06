"""Admin-only pipeline builder and plugin workshop API."""

from __future__ import annotations

import ipaddress
import json
import os
import logging
import threading
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from evileye.api.core.client_ip import resolve_client_ip
from evileye.api.core.rate_guard import load_protection_config
from evileye.api.security import require_role
from evileye.core.extension_builder import (
    PluginScaffoldError,
    create_plugin_operation,
    extension_catalog,
    get_plugin_operation,
    list_plugin_operations,
    plugin_operation_archive,
    preview_pipeline,
    save_pipeline,
    set_plugin_disabled,
)

logger = logging.getLogger("evileye.api.extensions")

router = APIRouter(prefix="/api/v1/admin/extensions", tags=["admin extensions"])


class PipelinePreviewRequest(BaseModel):
    config: dict[str, Any]


class PipelineSaveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    config: dict[str, Any]
    create_only: bool = True


class PluginCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    template: str = "processor"
    password: str = Field(min_length=1, max_length=256)


class PluginDisableRequest(BaseModel):
    disabled: bool


def _localhost_only() -> bool:
    value = os.getenv("EVILEYE_BUILDER_LOCALHOST_ONLY")
    if value is None:
        return True
    return value.strip().lower() not in {"0", "false", "no", "off"}


_PROXY_HEADERS = ("x-forwarded-for", "forwarded", "x-real-ip")
_protection_cache: dict[str, tuple[int, int, Any]] = {}
_protection_cache_lock = threading.Lock()


def _protection_config() -> Any:
    """Protection settings, re-read only when credentials.json changes on disk."""
    from evileye.core.paths import creds_path

    credentials_path = creds_path()
    try:
        stat = credentials_path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        signature = (0, 0)
    key = str(credentials_path)
    with _protection_cache_lock:
        cached = _protection_cache.get(key)
        if cached is not None and cached[:2] == signature:
            return cached[2]
    payload = json.loads(credentials_path.read_text(encoding="utf-8")) if signature != (0, 0) else {}
    auth_section = payload.get("web_auth", {}) if isinstance(payload, dict) else {}
    config = load_protection_config(auth_section if isinstance(auth_section, dict) else {})
    with _protection_cache_lock:
        _protection_cache[key] = (*signature, config)
    return config


def _address_allowed(address: str, entries: list[str]) -> bool:
    ip = ipaddress.ip_address(address)
    for entry in entries:
        try:
            if "/" in entry:
                if ip in ipaddress.ip_network(entry, strict=False):
                    return True
            elif ip == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False


def _assert_builder_access(request: Request) -> dict[str, Any]:
    user = require_role(request, {"admin"})
    if not _localhost_only():
        return user
    denied = HTTPException(status_code=403, detail="This admin workspace is available from localhost only")
    try:
        config = _protection_config()
    except Exception as exc:
        raise denied from exc
    # Without a trusted proxy the TCP peer is the only truthful address. A request that
    # carries forwarding headers was relayed by a proxy, so a loopback peer would be the
    # proxy itself and says nothing about the real client.
    if not config.trust_proxy and any(request.headers.get(name) for name in _PROXY_HEADERS):
        raise HTTPException(
            status_code=403,
            detail=(
                "The admin workspace rejects proxied requests; configure web_auth.protection."
                "trust_proxy with trusted_proxy_ips and builder_allowed_ips"
            ),
        )
    try:
        address = resolve_client_ip(
            request,
            trust_proxy=config.trust_proxy,
            trusted_proxy_ips=config.trusted_proxy_ips,
        )
        if not (ipaddress.ip_address(address).is_loopback or _address_allowed(address, config.builder_allowed_ips)):
            raise ValueError("address is not allowed")
    except Exception as exc:
        raise denied from exc
    return user


class _PasswordAttemptLimiter:
    """Locks password re-entry for a user or client address after repeated failures.

    Deliberately separate from the site-wide IP ban: a mistyped confirmation must not lock
    an administrator out of the whole UI, only out of this action.
    """

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}

    def retry_after(self, keys: list[str]) -> int:
        now = self._clock()
        with self._lock:
            remaining = [self._locked_until.get(key, 0.0) - now for key in keys]
            for key in keys:
                if self._locked_until.get(key, 0.0) <= now:
                    self._locked_until.pop(key, None)
        longest = max(remaining + [0.0])
        return int(longest) + 1 if longest > 0 else 0

    def record_failure(self, keys: list[str], *, max_failures: int, window_sec: float, lock_sec: float) -> int:
        """Record a failure; returns the lock duration in seconds when a lock started, else 0."""
        now = self._clock()
        locked = 0
        with self._lock:
            for key in keys:
                recent = [t for t in self._failures.get(key, []) if now - t < window_sec]
                recent.append(now)
                self._failures[key] = recent
                if len(recent) >= max_failures:
                    self._locked_until[key] = now + lock_sec
                    self._failures.pop(key, None)
                    locked = int(lock_sec)
        return locked

    def reset(self, keys: list[str]) -> None:
        with self._lock:
            for key in keys:
                self._failures.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._failures.clear()
            self._locked_until.clear()


_password_limiter = _PasswordAttemptLimiter()


def reset_password_limiter_for_tests(limiter: _PasswordAttemptLimiter | None = None) -> None:
    global _password_limiter
    _password_limiter = limiter or _PasswordAttemptLimiter()


def _too_many_attempts(seconds: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail=f"Too many failed password confirmations; try again in {seconds} s",
        headers={"Retry-After": str(seconds)},
    )


def _confirm_password(user: dict[str, Any], password: str, request: Request) -> None:
    """Re-authenticate the admin before an action that installs code.

    Failures are limited per user and per client address (see ``builder_password_*``).
    """
    from evileye.api.security import authenticate_user, load_web_auth_config

    username = str(user.get("username") or "")
    try:
        config = _protection_config()
        client = resolve_client_ip(
            request, trust_proxy=config.trust_proxy, trusted_proxy_ips=config.trusted_proxy_ips
        )
    except Exception:
        config, client = load_protection_config({}), "unknown"
    keys = [f"user:{username.lower()}", f"ip:{client}"]
    wait = _password_limiter.retry_after(keys)
    if wait:
        raise _too_many_attempts(wait)
    if username and authenticate_user(username, password, load_web_auth_config()) is not None:
        _password_limiter.reset(keys)
        return
    locked = _password_limiter.record_failure(
        keys,
        max_failures=int(config.builder_password_max_failures),
        window_sec=float(config.builder_password_window_sec),
        lock_sec=float(config.builder_password_lock_sec),
    )
    if locked:
        logger.warning(
            "Plugin install password confirmation locked for %s s (user=%s ip=%s)", locked, username, client
        )
        raise _too_many_attempts(locked)
    raise HTTPException(status_code=403, detail="Password confirmation failed")


@router.get("/catalog")
def get_extension_catalog(request: Request) -> dict[str, Any]:
    _assert_builder_access(request)
    try:
        return extension_catalog()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extension catalog failed: {exc}") from exc


@router.post("/preview")
def preview_pipeline_config(payload: PipelinePreviewRequest, request: Request) -> dict[str, Any]:
    _assert_builder_access(request)
    try:
        return preview_pipeline(payload.config)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/configs")
def save_pipeline_config(payload: PipelineSaveRequest, request: Request) -> dict[str, Any]:
    _assert_builder_access(request)
    try:
        return save_pipeline(payload.name, payload.config, create_only=payload.create_only)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline configuration save failed: {exc}") from exc


@router.post("/plugins")
def create_plugin(payload: PluginCreateRequest, request: Request) -> dict[str, Any]:
    user = _assert_builder_access(request)
    _confirm_password(user, payload.password, request)
    try:
        return create_plugin_operation(payload.name, payload.template)
    except PluginScaffoldError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Plugin creation failed: {exc}") from exc


@router.post("/plugins/{name}/disabled")
def set_plugin_disabled_state(name: str, payload: PluginDisableRequest, request: Request) -> dict[str, Any]:
    _assert_builder_access(request)
    try:
        return set_plugin_disabled(name, payload.disabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/operations/{operation_id}")
def get_extension_operation(operation_id: str, request: Request) -> dict[str, Any]:
    _assert_builder_access(request)
    try:
        return get_plugin_operation(operation_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Extension operation not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/operations")
def list_extension_operations(request: Request) -> list[dict[str, Any]]:
    _assert_builder_access(request)
    try:
        return list_plugin_operations()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extension operation history failed: {exc}") from exc


@router.get("/operations/{operation_id}/archive")
def download_plugin_archive(operation_id: str, request: Request):
    _assert_builder_access(request)
    try:
        operation = get_plugin_operation(operation_id)
        archive = plugin_operation_archive(operation_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Plugin archive not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(
        path=archive,
        media_type="application/zip",
        filename=f"evileye-plugin-{operation.get('name', operation_id)}.zip",
    )
