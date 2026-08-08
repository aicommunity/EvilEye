"""Early IP ban + global rate limiting middleware."""
from __future__ import annotations

import json

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from evileye.api.core.ip_ban_store import get_ip_ban_store
from evileye.api.core.rate_guard import get_rate_guard


def _ban_response(ban: dict) -> Response:
    payload = {
        "detail": "IP banned",
        "ban_id": ban.get("id"),
        "expires_at": ban.get("expires_at"),
    }
    return Response(json.dumps(payload), status_code=403, media_type="application/json")


class ProtectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        guard = get_rate_guard()
        if not guard.config.enabled:
            return await call_next(request)

        ip = guard.client_ip(request)
        ban = get_ip_ban_store().find_active_ban(ip)
        if ban is not None:
            return _ban_response(ban)

        skip_global = (
            path == "/ready"
            or path.startswith("/assets/")
            or (not path.startswith("/api/"))
        )
        # Valid internal relay traffic should not burn global budget.
        if path.startswith("/api/v1/internal/"):
            auth = getattr(request.app.state, "web_auth", None)
            token = getattr(auth, "internal_token", "") if auth else ""
            supplied = request.headers.get("X-EvilEye-Internal-Token", "")
            if token and supplied == token:
                skip_global = True

        if not skip_global:
            if guard.record_global_request(request):
                ban = get_ip_ban_store().find_active_ban(ip)
                if ban is not None:
                    return _ban_response(ban)

        response = await call_next(request)
        if response.status_code in {401, 403} and path.startswith("/api/v1/"):
            if path != "/api/v1/auth/login":
                guard.record_auth_fail_status(request)
        return response
