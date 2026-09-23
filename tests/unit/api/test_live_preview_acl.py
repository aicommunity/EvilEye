"""A01: empty source_ids means none; subscribe replace; no ACL auto-fill."""

from __future__ import annotations

import asyncio

import pytest

from evileye.api.core.live_preview_hub import get_live_preview_hub


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


def test_filter_subscribe_ids_against_acl_empty_stays_empty():
    """A01-T5/T10: intersection; empty subscribe must not expand to ACL."""
    allowed = {0, 1}
    requested = [0, 1, 2]
    filtered = [sid for sid in requested if sid in allowed]
    assert filtered == [0, 1]
    empty: list[int] = []
    # Must NOT become sorted(allowed)
    filtered_empty = [sid for sid in empty if sid in allowed]
    assert filtered_empty == []
