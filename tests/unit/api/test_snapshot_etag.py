"""Snapshot ETag / 304 support (A14) and missing-source 404 (A02)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from evileye.api.middleware.adaptive_session import AdaptiveSessionMiddleware
from evileye.api.routes import streaming as streaming_routes
from evileye.core.runtime_services import get_frame_broker


@pytest.fixture
def snapshot_client(monkeypatch):
    app = FastAPI()
    app.add_middleware(
        AdaptiveSessionMiddleware,
        secret_key="x" * 32,
        session_cookie="evileye_session",
        secure_cookies=False,
    )

    @app.post("/login")
    async def login(request: Request):
        request.session["user"] = {"username": "admin", "role": "admin"}
        return {"ok": True}

    app.include_router(streaming_routes.router)
    app.state.preview_demand_queue = None
    # Auth disabled → camera ACL unrestricted (see resolve_camera_access).
    app.state.web_auth = None

    run_info = {"id": 7, "state": "running", "sources": [{"source_id": 0, "source_name": "Cam1"}]}

    monkeypatch.setattr(streaming_routes, "_resolve_run", lambda rid: run_info)
    monkeypatch.setattr(streaming_routes, "_require_source_id_if_multi", lambda *_a, **_k: None)

    broker = get_frame_broker()
    broker.publish_jpeg("7:0", b"jpeg-bytes-v1", metadata={"source_id": 0, "etag": "v1"})

    client = TestClient(app)
    assert client.post("/login").status_code == 200
    return client


def test_snapshot_returns_etag(snapshot_client):
    res = snapshot_client.get("/api/v1/runs/7/snapshot?source_id=0")
    assert res.status_code == 200
    assert res.headers.get("etag")
    assert res.content == b"jpeg-bytes-v1"


def test_snapshot_304_when_etag_matches(snapshot_client):
    first = snapshot_client.get("/api/v1/runs/7/snapshot?source_id=0")
    etag = first.headers["etag"]
    second = snapshot_client.get(
        "/api/v1/runs/7/snapshot?source_id=0",
        headers={"If-None-Match": etag},
    )
    assert second.status_code == 304
    assert second.content == b""


def test_snapshot_200_when_jpeg_changes(snapshot_client):
    first = snapshot_client.get("/api/v1/runs/7/snapshot?source_id=0")
    etag = first.headers["etag"]
    get_frame_broker().publish_jpeg("7:0", b"jpeg-bytes-v2", metadata={"source_id": 0, "etag": "v2"})
    second = snapshot_client.get(
        "/api/v1/runs/7/snapshot?source_id=0",
        headers={"If-None-Match": etag},
    )
    assert second.status_code == 200
    assert second.content == b"jpeg-bytes-v2"
    assert second.headers["etag"] != etag


def test_snapshot_missing_source_id_returns_404_not_run_level(snapshot_client, monkeypatch):
    """A02: explicit source_id must not fall back to run-level JPEG."""
    broker = get_frame_broker()
    # Only run-level frame (wrong camera content).
    broker.publish_jpeg("7", b"camera-one", metadata={"source_id": 1, "etag": "other"})
    # Ensure no per-source key for 0
    try:
        if hasattr(broker, "_frames"):
            broker._frames.pop("7:0", None)
    except Exception:
        pass

    res = snapshot_client.get("/api/v1/runs/7/snapshot?source_id=0")
    # After A02 fix: 404. Before fix this returned 200 + camera-one.
    assert res.status_code == 404
    assert res.content != b"camera-one"
