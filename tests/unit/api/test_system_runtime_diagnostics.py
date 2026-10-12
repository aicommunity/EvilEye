import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from evileye.api.routes import system
from evileye.api.security import required_permissions_for_request


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/api/v1/system/runtime", "headers": []})


def test_system_runtime_returns_stats_from_controller_ipc(monkeypatch, tmp_path):
    def require_runtime_view(request, permission):
        assert permission == "runtime:view"
        return {"role": "admin"}

    monkeypatch.setattr(system, "require_permission", require_runtime_view)
    socket_path = tmp_path / "control.sock"
    socket_path.touch()
    monkeypatch.setattr("evileye.api.core.control_ipc.control_socket_path", lambda: socket_path)
    monkeypatch.setattr(
        "evileye.api.core.control_ipc.send_control_command",
        lambda command, *, timeout: {
            "ok": True,
            "stats": {"available": True, "degraded": False, "components": {"pipeline": {"degraded": False}}},
        },
    )

    result = asyncio.run(system.system_runtime(_request()))

    assert result == {
        "available": True,
        "degraded": False,
        "components": {"pipeline": {"degraded": False}},
    }


def test_system_runtime_returns_503_when_controller_is_not_running(monkeypatch, tmp_path):
    monkeypatch.setattr(system, "require_permission", lambda request, permission: {"role": "admin"})
    monkeypatch.setattr("evileye.api.core.control_ipc.control_socket_path", lambda: tmp_path / "missing.sock")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(system.system_runtime(_request()))

    assert exc.value.status_code == 503



def test_system_runtime_route_requires_runtime_view_permission():
    assert required_permissions_for_request("/api/v1/system/runtime", "GET") == {"runtime:view"}
