"""Unit: live preview hub kicks clients by username (R08)."""

from __future__ import annotations

from unittest.mock import MagicMock

from evileye.api.core.live_preview_hub import LivePreviewClient, LivePreviewHub


def test_unregister_username_closes_matching_clients():
    hub = LivePreviewHub()
    hub._loop = MagicMock()
    hub._loop.create_task = MagicMock()
    ws_a = MagicMock()
    ws_b = MagicMock()
    a = LivePreviewClient(websocket=ws_a, run_id=1, username="ops")
    b = LivePreviewClient(websocket=ws_b, run_id=1, username="admin")
    hub._clients = [a, b]
    closed = hub.unregister_username("ops")
    assert closed == 1
    assert a.closed is True
    assert len(hub._clients) == 1
    assert hub._clients[0].username == "admin"
