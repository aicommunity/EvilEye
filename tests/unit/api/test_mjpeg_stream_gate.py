"""MJPEG stream starts without a pre-existing broker frame (no 409)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from evileye.core.runtime_services import get_frame_broker
from evileye.api.routes import streaming as streaming_routes


@pytest.fixture
def mjpeg_app(monkeypatch):
    app = FastAPI()
    app.include_router(streaming_routes.router)
    app.state.preview_demand_queue = None

    run_info = {"id": 11, "state": "running", "sources": [{"source_id": 0, "source_name": "Cam1"}]}

    monkeypatch.setattr(streaming_routes, "_resolve_run", lambda rid: run_info)
    monkeypatch.setattr(streaming_routes, "_require_source_id_if_multi", lambda *_a, **_k: None)
    monkeypatch.setenv("EVILEYE_MJPEG_IDLE_SEC", "0.3")
    monkeypatch.setenv("EVILEYE_MAX_MJPEG_CLIENTS", "8")
    streaming_routes._mjpeg_clients = 0

    broker = get_frame_broker()
    with broker._lock:
        broker._frames.pop("11", None)
        broker._frames.pop("11:0", None)

    return app, run_info


def test_mjpeg_starts_without_frame_returns_200(mjpeg_app):
    app, _ = mjpeg_app
    client = TestClient(app)

    # Empty broker must not 409 — stream opens and waits until idle timeout.
    res = client.get("/api/v1/runs/11/stream.mjpg?source_id=0&fps=5")
    assert res.status_code == 200
    assert "multipart" in (res.headers.get("content-type") or "")


def test_mjpeg_rejects_when_run_not_running(mjpeg_app, monkeypatch):
    app, _ = mjpeg_app

    def _resolve(rid):
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="not running")

    monkeypatch.setattr(streaming_routes, "_resolve_run", _resolve)
    client = TestClient(app)
    res = client.get("/api/v1/runs/11/stream.mjpg?source_id=0")
    assert res.status_code == 400


def test_mjpeg_503_when_slots_exhausted(mjpeg_app, monkeypatch):
    app, _ = mjpeg_app
    monkeypatch.setenv("EVILEYE_MAX_MJPEG_CLIENTS", "1")
    streaming_routes._mjpeg_clients = 1
    try:
        client = TestClient(app)
        res = client.get("/api/v1/runs/11/stream.mjpg?source_id=0")
        assert res.status_code == 503
    finally:
        streaming_routes._mjpeg_clients = 0


def test_should_attach_mjpeg_logic():
    """Mirrors frontend shouldAttachMjpeg helper."""

    def should_attach(status, elapsed_ms, warm_ms=5000):
        if status and (status.get("has_frame") or status.get("web_stream_available")):
            return True
        return elapsed_ms >= warm_ms

    assert should_attach({"has_frame": True}, 0) is True
    assert should_attach({"web_stream_available": True}, 0) is True
    assert should_attach({"has_frame": False}, 1000) is False
    assert should_attach(None, 5000) is True
