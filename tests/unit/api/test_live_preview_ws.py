"""Live grid preview WebSocket hub + auth helpers."""

import asyncio
from types import SimpleNamespace

import pytest

from evileye.api.core.live_preview_hub import get_live_preview_hub
from evileye.api.routes import realtime as realtime_routes


@pytest.fixture(autouse=True)
def reset_live_preview_hub(monkeypatch):
    monkeypatch.delenv("EVILEYE_WS_PREVIEW_MODE", raising=False)
    monkeypatch.delenv("EVILEYE_WS_PREVIEW_SEND_TIMEOUT_SEC", raising=False)
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
    hub._stats = {
        "clients": 0,
        "bytes_sent": 0,
        "messages": 0,
        "dropped": 0,
        "client_timeouts": 0,
        "client_replaced": 0,
        "clients_kicked": 0,
    }
    yield
    for client in list(hub._clients):
        hub.unregister(client)


def test_hub_fanout_subscribed_source():
    async def _run():
        hub = get_live_preview_hub()
        loop = asyncio.get_running_loop()
        hub.start(loop)

        sent_json: list[dict] = []
        sent_bytes: list[bytes] = []

        class _FakeWs:
            async def send_json(self, payload):
                sent_json.append(payload)

            async def send_bytes(self, payload: bytes):
                sent_bytes.append(payload)

        client = await hub.register(_FakeWs(), 7)
        assert client is not None
        hub.set_client_sources(client, [1])

        hub.on_broker_publish("7:1", b"jpeg-bytes", {"etag": "e1", "ts": 1.0})
        await asyncio.sleep(0.1)

        assert sent_json
        assert sent_json[0]["type"] == "preview"
        assert sent_json[0]["source_id"] == 1
        assert sent_bytes == [b"jpeg-bytes"]

        hub.on_broker_publish("7:2", b"other", {"etag": "e2"})
        await asyncio.sleep(0.1)
        assert len(sent_bytes) == 1

    asyncio.run(_run())


def test_hub_skips_full_frame_keys():
    async def _run():
        hub = get_live_preview_hub()
        loop = asyncio.get_running_loop()
        hub.start(loop)
        sent_bytes: list[bytes] = []

        class _FakeWs:
            async def send_json(self, payload):
                return None

            async def send_bytes(self, payload: bytes):
                sent_bytes.append(payload)

        client = await hub.register(_FakeWs(), 7)
        hub.set_client_sources(client, [1])
        hub.on_broker_publish("7:full:1", b"full-jpeg", {"etag": "f1", "ts": 1.0, "full_frame": True})
        hub.on_broker_publish("7:1", b"crop-jpeg", {"etag": "c1", "ts": 1.0})
        await asyncio.sleep(0.1)
        assert sent_bytes == [b"crop-jpeg"]

    asyncio.run(_run())


def test_hub_notify_mode_skips_binary(monkeypatch):
    monkeypatch.setenv("EVILEYE_WS_PREVIEW_MODE", "notify")

    async def _run():
        hub = get_live_preview_hub()
        loop = asyncio.get_running_loop()
        hub.start(loop)
        sent_json: list[dict] = []
        sent_bytes: list[bytes] = []

        class _FakeWs:
            async def send_json(self, payload):
                sent_json.append(payload)

            async def send_bytes(self, payload: bytes):
                sent_bytes.append(payload)

        client = await hub.register(_FakeWs(), 7)
        hub.set_client_sources(client, [0])
        hub.on_broker_publish("7:0", b"jpeg", {"etag": "n1"})
        await asyncio.sleep(0.1)
        assert sent_json[0]["type"] == "preview_notify"
        assert sent_bytes == []

    asyncio.run(_run())


def test_hub_skips_duplicate_etag():
    async def _run():
        hub = get_live_preview_hub()
        loop = asyncio.get_running_loop()
        hub.start(loop)

        sent_bytes: list[bytes] = []

        class _FakeWs:
            async def send_json(self, payload):
                pass

            async def send_bytes(self, payload: bytes):
                sent_bytes.append(payload)

        client = await hub.register(_FakeWs(), 7)
        hub.set_client_sources(client, [0])
        hub.on_broker_publish("7:0", b"a", {"etag": "same"})
        hub.on_broker_publish("7:0", b"b", {"etag": "same"})
        await asyncio.sleep(0.1)
        assert len(sent_bytes) == 1

    asyncio.run(_run())


class _FakeAuthWs:
    def __init__(self):
        self.closed = None
        self.scope = {"session": {}}
        self.app = SimpleNamespace(state=SimpleNamespace(preview_demand_queue=None))

    async def close(self, code: int = 1000):
        self.closed = code


def test_authorize_live_ws_4401(monkeypatch):
    class _Auth:
        enabled = True

    monkeypatch.setattr(realtime_routes, "load_web_auth_config", lambda: _Auth())

    def _boom(_ws):
        raise Exception("no session")

    monkeypatch.setattr(realtime_routes, "current_user", _boom)
    ws = _FakeAuthWs()

    async def _run():
        ok = await realtime_routes._authorize_live_ws(ws)
        assert ok is False
        assert ws.closed == 4401

    asyncio.run(_run())


def test_authorize_live_ws_4403(monkeypatch):
    class _Auth:
        enabled = True

    monkeypatch.setattr(realtime_routes, "load_web_auth_config", lambda: _Auth())
    monkeypatch.setattr(
        realtime_routes,
        "current_user",
        lambda _ws: {"role": "user", "permissions": []},
    )
    monkeypatch.setattr(realtime_routes, "permissions_for_role", lambda _r: set())
    ws = _FakeAuthWs()

    async def _run():
        ok = await realtime_routes._authorize_live_ws(ws)
        assert ok is False
        assert ws.closed == 4403

    asyncio.run(_run())


def test_hub_register_rejects_when_full():
    async def _run():
        hub = get_live_preview_hub()
        hub._max_clients = 1

        class _FakeWs:
            pass

        first = await hub.register(_FakeWs(), 7)
        second = await hub.register(_FakeWs(), 7)
        assert first is not None
        assert second is None

    asyncio.run(_run())


def test_hub_slow_client_does_not_block_fast_client(monkeypatch):
    """A slow WAN send must not stall fan-out to other subscribers."""
    monkeypatch.setenv("EVILEYE_WS_PREVIEW_SEND_TIMEOUT_SEC", "0.3")

    async def _run():
        hub = get_live_preview_hub()
        loop = asyncio.get_running_loop()
        hub.start(loop)

        fast_bytes: list[bytes] = []
        slow_started = asyncio.Event()

        class _FastWs:
            async def send_json(self, payload):
                return None

            async def send_bytes(self, payload: bytes):
                fast_bytes.append(payload)

        class _SlowWs:
            async def send_json(self, payload):
                slow_started.set()
                await asyncio.sleep(5.0)

            async def send_bytes(self, payload: bytes):
                return None

        slow = await hub.register(_SlowWs(), 7)
        fast = await hub.register(_FastWs(), 7)
        assert slow is not None and fast is not None
        hub.set_client_sources(slow, [0])
        hub.set_client_sources(fast, [0])

        hub.on_broker_publish("7:0", b"frame-a", {"etag": "a", "ts": 1.0})
        await asyncio.wait_for(slow_started.wait(), timeout=1.0)
        # While slow client is blocked mid-send, enqueue another frame for both.
        hub.on_broker_publish("7:0", b"frame-b", {"etag": "b", "ts": 2.0})
        await asyncio.sleep(0.15)

        assert b"frame-b" in fast_bytes or b"frame-a" in fast_bytes
        # Fast client should have progressed; slow may still be stuck / kicked later.
        assert len(fast_bytes) >= 1

        # Wait for slow client timeout kick.
        await asyncio.sleep(0.5)
        assert slow not in hub._clients or slow.closed
        assert hub.stats()["client_timeouts"] >= 1

    asyncio.run(_run())


def test_hub_latest_wins_replaces_pending(monkeypatch):
    monkeypatch.setenv("EVILEYE_WS_PREVIEW_SEND_TIMEOUT_SEC", "2.0")

    async def _run():
        hub = get_live_preview_hub()
        loop = asyncio.get_running_loop()
        hub.start(loop)

        gate = asyncio.Event()
        sent_bytes: list[bytes] = []

        class _GatedWs:
            async def send_json(self, payload):
                await gate.wait()

            async def send_bytes(self, payload: bytes):
                sent_bytes.append(payload)

        client = await hub.register(_GatedWs(), 7)
        hub.set_client_sources(client, [0])

        hub.on_broker_publish("7:0", b"old", {"etag": "1", "ts": 1.0})
        # Let sender pick up first frame and block on send_json.
        await asyncio.sleep(0.05)
        hub.on_broker_publish("7:0", b"mid", {"etag": "2", "ts": 2.0})
        hub.on_broker_publish("7:0", b"new", {"etag": "3", "ts": 3.0})
        await asyncio.sleep(0.05)
        assert hub.stats()["client_replaced"] >= 1
        gate.set()
        await asyncio.sleep(0.15)
        # First in-flight frame may still complete; later pending collapsed to latest.
        assert b"new" in sent_bytes
        assert sent_bytes[-1] == b"new"

    asyncio.run(_run())
