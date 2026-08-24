"""Resolve public API base URL without trusting request Host headers."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

from evileye.core.paths import creds_path

_BIND_ALL_HOSTS = frozenset({"0.0.0.0", "::", "[::]"})


def _load_credentials() -> dict[str, Any]:
    path = creds_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def canonicalize_relay_base_url(url: str) -> str:
    """Replace bind-all hosts with loopback so urllib can connect."""
    raw = (url or "").strip()
    if not raw:
        return raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host not in _BIND_ALL_HOSTS:
        return raw.rstrip("/")
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    netloc = f"127.0.0.1:{port}"
    return urlunparse(parsed._replace(netloc=netloc)).rstrip("/")


def resolve_public_api_base_url(*, port: Optional[int] = None) -> str:
    """
    Priority:
    1. EVILEYE_WEB_API_BASE env
    2. credentials.json server.public_base_url (with /api/v1 appended if needed)
    3. configs/system.json server.public_base_url
    4. http(s)://127.0.0.1:{port}/api/v1  (https when TLS files/env are set)
    """
    from evileye.api.core.ssl_files import SslConfigError, load_system_server_cfg, resolve_ssl_files, ssl_enabled

    env = (os.getenv("EVILEYE_WEB_API_BASE") or "").strip().rstrip("/")
    if env:
        base = env if env.endswith("/api/v1") else f"{env}/api/v1"
        return canonicalize_relay_base_url(base)

    creds = _load_credentials()
    server = creds.get("server") if isinstance(creds.get("server"), dict) else {}
    configured = str(server.get("public_base_url") or "").strip().rstrip("/")
    if configured:
        return configured if configured.endswith("/api/v1") else f"{configured}/api/v1"

    sys_server = load_system_server_cfg()
    configured = str(sys_server.get("public_base_url") or "").strip().rstrip("/")
    if configured:
        return configured if configured.endswith("/api/v1") else f"{configured}/api/v1"

    listen_port = port
    if listen_port is None:
        try:
            listen_port = int(os.getenv("EVILEYE_HTTP_PORT") or server.get("port") or sys_server.get("port") or 8181)
        except (TypeError, ValueError):
            listen_port = 8181
    scheme = "http"
    try:
        cert, key = resolve_ssl_files(server_cfg=sys_server)
        if ssl_enabled(cert, key):
            scheme = "https"
    except SslConfigError:
        pass
    return f"{scheme}://127.0.0.1:{listen_port}/api/v1"
