"""Unit tests for internal frame metadata relay (no TestClient/httpx required)."""
from __future__ import annotations

import io
import json
from contextlib import contextmanager

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
            "transport": "should_be_ignored",
        },
    )
    assert meta["source_id"] == 3
    assert meta["transport"] == "http_internal"
    assert meta["objects"][0]["track_id"] == 1
    assert meta["signalization"] is True


def test_broker_keeps_overlay_metadata():
    broker = get_frame_broker()
    meta = _merge_metadata(
        source_id=7,
        content_type="image/jpeg",
        extra={"objects": [{"track_id": 9}], "zones": [], "signalization": False},
    )
    broker.publish_jpeg("55:7", b"\xff\xd8fake", metadata=meta)
    out = broker.latest_metadata("55:7")
    assert out is not None
    assert out["objects"][0]["track_id"] == 9


def test_frame_relay_multipart_payload(monkeypatch):
    captured: dict = {}

    @contextmanager
    def fake_urlopen(req, timeout=None):  # noqa: ARG001
        captured["url"] = req.full_url
        captured["data"] = req.data
        captured["content_type"] = req.headers.get("Content-type") or req.headers.get("Content-Type")

        class Resp:
            status = 200

        yield Resp()

    monkeypatch.setattr(
        "evileye.controller.services.streaming_service.urllib.request.urlopen",
        fake_urlopen,
    )
    client = FrameRelayClient("http://127.0.0.1:8181", token="tok")
    ok = client.publish_jpeg(
        "12",
        b"\xff\xd8jpg",
        source_id=2,
        metadata={"objects": [{"track_id": 1}], "zones": [], "signalization": True},
    )
    assert ok is True
    assert "source_id=2" in captured["url"]
    assert "multipart/form-data" in (captured["content_type"] or "")
    assert b"metadata" in captured["data"]
    assert b"track_id" in captured["data"]
    assert b"\xff\xd8jpg" in captured["data"]
    # Ensure JSON is parseable from multipart body
    assert b'"signalization":true' in captured["data"] or b'"signalization": true' in captured["data"]
