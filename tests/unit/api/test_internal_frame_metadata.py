"""Unit tests for internal frame metadata relay (no TestClient/httpx required)."""
from __future__ import annotations

import time

from evileye.api.routes.internal import _merge_metadata
from evileye.controller.services.streaming_service import FrameRelayClient
from evileye.core.runtime_services import get_frame_broker


def test_merge_metadata_preserves_overlays():
    meta = _merge_metadata(
        source_id=3,
        content_type="image/jpeg",
        extra={
            "objects": [{"track_id": 1, "bbox": [0.1, 0.1, 0.2, 0.2]}],
            "zones": [{"name": "z", "points": [[0, 0], [1, 0], [1, 1]]}],
            "signalization": True,
            "event_labels": ["ZoneEvent [1]"],
            "overlay": {"source_name": "Cam0"},
            "transport": "should_be_ignored",
        },
    )
    assert meta["source_id"] == 3
    assert meta["transport"] == "http_internal"
    assert meta["objects"][0]["track_id"] == 1
    assert meta["signalization"] is True
    assert meta["event_labels"] == ["ZoneEvent [1]"]
    assert meta["overlay"]["source_name"] == "Cam0"


def test_broker_keeps_overlay_metadata():
    broker = get_frame_broker()
    meta = _merge_metadata(
        source_id=7,
        content_type="image/jpeg",
        extra={
            "objects": [{"track_id": 9}],
            "zones": [],
            "signalization": False,
            "event_labels": ["AttributeEvent [9]"],
        },
    )
    broker.publish_jpeg("55:7", b"\xff\xd8fake", metadata=meta)
    out = broker.latest_metadata("55:7")
    assert out is not None
    assert out["objects"][0]["track_id"] == 9
    assert out["event_labels"] == ["AttributeEvent [9]"]


def test_internal_relay_target_url_without_socket_file(tmp_path, monkeypatch):
    from evileye.api.core.internal_unix import internal_relay_target_url, internal_relay_url

    monkeypatch.setattr("evileye.api.core.internal_unix.internal_socket_path", lambda: tmp_path / "internal.sock")
    assert internal_relay_url() is None
    assert internal_relay_target_url() == f"unix://{tmp_path / 'internal.sock'}"


def test_frame_relay_jpeg_and_metadata_header():
    from evileye.api.core.internal_unix import (
        internal_socket_path,
        start_internal_unix_server,
        stop_internal_unix_server,
    )

    start_internal_unix_server("tok")
    try:
        broker = get_frame_broker()
        client = FrameRelayClient(f"unix://{internal_socket_path()}", token="tok")
        ok = client.publish_jpeg(
            "12",
            b"\xff\xd8jpg",
            source_id=2,
            metadata={"objects": [{"track_id": 1}], "zones": [], "signalization": True},
        )
        assert ok is True
        deadline = time.time() + 1.0
        meta = None
        while time.time() < deadline:
            meta = broker.latest_metadata("12:2")
            if meta:
                break
            time.sleep(0.02)
        client.close()
        assert meta is not None
        assert meta["objects"][0]["track_id"] == 1
        assert meta["signalization"] is True
    finally:
        stop_internal_unix_server()


def test_frame_relay_https_url_is_ignored():
    client = FrameRelayClient("https://127.0.0.1:8181/api/v1", token="tok")
    try:
        assert client._unix_path() is None
        assert client._post("1", b"\xff\xd8jpg", source_id=0, metadata={"objects": []}) is False
    finally:
        client.close()
