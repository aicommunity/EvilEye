"""Resolve client IP with optional trusted-proxy support."""
from __future__ import annotations

from typing import Any, Optional, Sequence


def resolve_client_ip(
    request: Any,
    *,
    trust_proxy: bool = False,
    trusted_proxy_ips: Optional[Sequence[str]] = None,
) -> str:
    peer = ""
    client = getattr(request, "client", None)
    if client is not None:
        peer = str(getattr(client, "host", "") or "").strip()

    if not trust_proxy:
        return peer or "unknown"

    trusted = {str(ip).strip() for ip in (trusted_proxy_ips or []) if str(ip).strip()}
    if peer and peer not in trusted:
        return peer or "unknown"

    headers = getattr(request, "headers", None) or {}
    forwarded = ""
    try:
        forwarded = str(headers.get("x-forwarded-for") or headers.get("X-Forwarded-For") or "").strip()
    except Exception:
        forwarded = ""
    if forwarded:
        # X-Forwarded-For: client, proxy1, proxy2 — take left-most untrusted / original client.
        # When the immediate peer is a trusted proxy, the client is the first hop in the chain.
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            # Walk from the right, skip trailing trusted proxies, then take the next (client).
            idx = len(parts) - 1
            while idx >= 0 and parts[idx] in trusted:
                idx -= 1
            if idx >= 0:
                return parts[idx]
            return parts[0]

    try:
        real_ip = str(headers.get("x-real-ip") or headers.get("X-Real-IP") or "").strip()
    except Exception:
        real_ip = ""
    if real_ip:
        return real_ip
    return peer or "unknown"
