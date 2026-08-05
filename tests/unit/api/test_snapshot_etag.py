"""Snapshot ETag / 304 support."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from evileye.api.core.frame_broker import get_frame_broker
from evileye.api.routes import streaming as streaming_routes


@pytest.fixture
def snapshot_client(monkeypatch):
    app = FastAPI()
    app.include_router(streaming_routes.router)
    app.state.preview_demand_queue = None

    run_info = {"id": 7, "state": "running", "sources": [{"source_id": 0, "source_name": "Cam1"}]}

    monkeypatch.setattr(streaming_routes, "_resolve_run", lambda rid: run_info)
    monkeypatch.setattr(streaming_routes, "_require_source_id_if_multi", lambda *_a, **_k: None)

    broker = get_frame_broker()
    broker.publish_jpeg("7:0", b"jpeg-bytes-v1", metadata={"source_id": 0})

    return TestClient(app)


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
    get_frame_broker().publish_jpeg("7:0", b"jpeg-bytes-v2", metadata={"source_id": 0})
    second = snapshot_client.get(
        "/api/v1/runs/7/snapshot?source_id=0",
        headers={"If-None-Match": etag},
    )
    assert second.status_code == 200
    assert second.content == b"jpeg-bytes-v2"
    assert second.headers["etag"] != etag
