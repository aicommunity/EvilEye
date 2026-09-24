"""A01: empty source_ids means none; subscribe replace; no ACL auto-fill; full matrix."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from evileye.api.core.camera_access import CameraAccess
from evileye.api.core.live_preview_hub import get_live_preview_hub
from evileye.api.routes import realtime as realtime_routes


@pytest.fixture(autouse=True)
def reset_hub(monkeypatch):
    monkeypatch.delenv("EVILEYE_WS_PREVIEW_MODE", raising=False)
    hub = get_live_preview_hub()
    for client in list(hub._clients):
        hub.unregister(client)
    hub._clients.clear()
    hub._max_clients = 32
    if hub._fanout_task is not None and not hub._fanout_task.done():
        hub._fanout_task.cancel()
    hub._fanout_task = None
    hub._loop = None
    hub._queue = asyncio.Queue(maxsize=256)
    yield
    for client in list(hub._clients):
        hub.unregister(client)


def test_hub_empty_source_ids_delivers_nothing():
    """A01-T1/T7: empty set = none, not all."""

    async def _run():
        hub = get_live_preview_hub()
        hub.start(asyncio.get_running_loop())
        sent: list[bytes] = []

        class _Ws:
            async def send_json(self, payload):
                return None

            async def send_bytes(self, payload: bytes):
                sent.append(payload)

        client = await hub.register(_Ws(), 7)
        assert client is not None
        assert client.source_ids == set()
        hub.on_broker_publish("7:0", b"a", {"etag": "e0"})
        hub.on_broker_publish("7:1", b"b", {"etag": "e1"})
        await asyncio.sleep(0.1)
        assert sent == []

    asyncio.run(_run())


def test_hub_subscribe_filters_and_empty_clears():
    """A01-T2/T3: only subscribed; empty subscribe → silence."""

    async def _run():
        hub = get_live_preview_hub()
        hub.start(asyncio.get_running_loop())
        sent: list[bytes] = []

        class _Ws:
            async def send_json(self, payload):
                return None

            async def send_bytes(self, payload: bytes):
                sent.append(payload)

        client = await hub.register(_Ws(), 7)
        hub.set_client_sources(client, [0])
        hub.on_broker_publish("7:0", b"ok", {"etag": "1"})
        hub.on_broker_publish("7:1", b"no", {"etag": "2"})
        await asyncio.sleep(0.1)
        assert sent == [b"ok"]

        hub.set_client_sources(client, [])
        hub.on_broker_publish("7:0", b"again", {"etag": "3"})
        await asyncio.sleep(0.1)
        assert sent == [b"ok"]

    asyncio.run(_run())


def test_hub_subscribe_replaces_set():
    """A01-T4: subscribe replaces previous set."""

    async def _run():
        hub = get_live_preview_hub()
        hub.start(asyncio.get_running_loop())
        sent_ids: list[int] = []

        class _Ws:
            async def send_json(self, payload):
                if payload.get("type") == "preview":
                    sent_ids.append(int(payload["source_id"]))

            async def send_bytes(self, payload: bytes):
                return None

        client = await hub.register(_Ws(), 7)
        hub.set_client_sources(client, [0, 1])
        hub.set_client_sources(client, [1])
        hub.on_broker_publish("7:0", b"a", {"etag": "a"})
        hub.on_broker_publish("7:1", b"b", {"etag": "b"})
        await asyncio.sleep(0.1)
        assert sent_ids == [1]

    asyncio.run(_run())


def test_hub_notify_mode_respects_empty_sources(monkeypatch):
    """A01-T8: notify mode also silent when empty."""
    monkeypatch.setenv("EVILEYE_WS_PREVIEW_MODE", "notify")

    async def _run():
        hub = get_live_preview_hub()
        hub.start(asyncio.get_running_loop())
        sent_json: list[dict] = []

        class _Ws:
            async def send_json(self, payload):
                sent_json.append(payload)

            async def send_bytes(self, payload: bytes):
                return None

        await hub.register(_Ws(), 7)
        hub.on_broker_publish("7:0", b"jpeg", {"etag": "n1"})
        await asyncio.sleep(0.1)
        assert sent_json == []

    asyncio.run(_run())


def test_hub_binary_delivers_when_subscribed():
    """A01 matrix: binary + subscribed → frame delivered."""

    async def _run():
        hub = get_live_preview_hub()
        hub.start(asyncio.get_running_loop())
        sent: list[bytes] = []

        class _Ws:
            async def send_json(self, payload):
                return None

            async def send_bytes(self, payload: bytes):
                sent.append(payload)

        client = await hub.register(_Ws(), 7)
        hub.set_client_sources(client, [0])
        hub.on_broker_publish("7:0", b"jpeg", {"etag": "b1"})
        await asyncio.sleep(0.1)
        assert sent == [b"jpeg"]

    asyncio.run(_run())


def test_filter_subscribe_ids_against_acl_empty_stays_empty():
    """A01-T5/T10: intersection; empty subscribe must not expand to ACL."""
    allowed = {0, 1}
    assert realtime_routes.filter_live_subscribe_ids(allowed, [0, 1, 2]) == [0, 1]
    assert realtime_routes.filter_live_subscribe_ids(allowed, []) == []
    assert realtime_routes.filter_live_subscribe_ids(allowed, [9]) == []
    # unrestricted
    assert realtime_routes.filter_live_subscribe_ids(None, [0, 9]) == [0, 9]


def test_live_preview_acl_rejects_empty_set():
    assert realtime_routes.live_preview_acl_rejects_empty(set()) is True
    assert realtime_routes.live_preview_acl_rejects_empty({0}) is False
    assert realtime_routes.live_preview_acl_rejects_empty(None) is False


def test_empty_acl_gate_closes_4403_without_register(monkeypatch):
    """Restricted empty ACL → 4403 before accept/register."""

    class _Ws:
        def __init__(self):
            self.closed = None
            self.accepted = False
            self.scope = {"session": {"user": {"username": "ops", "role": "user"}}}

        async def close(self, code: int = 1000):
            self.closed = code

        async def accept(self):
            self.accepted = True

        async def receive_text(self):
            raise AssertionError("must not receive after reject")

    monkeypatch.setattr(realtime_routes, "_authorize_live_ws", lambda _ws: _async_true())
    monkeypatch.setattr(
        realtime_routes,
        "_resolve_run",
        lambda _rid: {"id": 7, "state": "running", "sources": []},
    )
    monkeypatch.setattr(
        realtime_routes,
        "_camera_access_from_websocket",
        lambda _ws: CameraAccess(
            unrestricted=False,
            allowed_names=frozenset(),
            visible_names=frozenset(),
        ),
    )

    async def _allowed(_access, _run_id):
        return set()

    monkeypatch.setattr(
        "evileye.api.core.camera_access.allowed_source_ids_for_run",
        lambda access, run_id: set(),
    )

    ws = _Ws()
    register_called = {"n": 0}
    hub = get_live_preview_hub()
    orig_register = hub.register

    async def _count_register(*a, **k):
        register_called["n"] += 1
        return await orig_register(*a, **k)

    monkeypatch.setattr(hub, "register", _count_register)

    async def _run():
        await realtime_routes.live_grid_preview_ws(ws, 7)

    asyncio.run(_run())
    assert ws.closed == 4403
    assert ws.accepted is False
    assert register_called["n"] == 0


async def _async_true():
    return True


def test_restricted_subscribe_filters_forbidden_ids():
    """Restricted: forbidden ids dropped; mixed list keeps allowed only."""
    allowed = {0}
    assert realtime_routes.filter_live_subscribe_ids(allowed, [1]) == []
    assert realtime_routes.filter_live_subscribe_ids(allowed, [0, 1]) == [0]


def test_admin_unrestricted_keeps_all_subscribe_ids():
    assert realtime_routes.filter_live_subscribe_ids(None, [0, 1, 99]) == [0, 1, 99]


def test_subscribe_acl_applied_then_hub_silence_for_forbidden():
    """End-to-end hub: after ACL filter, forbidden source never fans out."""

    async def _run():
        hub = get_live_preview_hub()
        hub.start(asyncio.get_running_loop())
        sent: list[bytes] = []

        class _Ws:
            async def send_json(self, payload):
                return None

            async def send_bytes(self, payload: bytes):
                sent.append(payload)

        client = await hub.register(_Ws(), 7)
        source_ids = realtime_routes.filter_live_subscribe_ids({0}, [0, 1])
        hub.set_client_sources(client, source_ids)
        hub.on_broker_publish("7:0", b"ok", {"etag": "1"})
        hub.on_broker_publish("7:1", b"no", {"etag": "2"})
        await asyncio.sleep(0.1)
        assert sent == [b"ok"]

    asyncio.run(_run())
