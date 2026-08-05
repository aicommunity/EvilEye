"""Live grid preview WebSocket hub + auth helpers."""

import asyncio
from types import SimpleNamespace

import pytest

from evileye.api.core.live_preview_hub import get_live_preview_hub
from evileye.api.routes import realtime as realtime_routes


@pytest.fixture(autouse=True)
def reset_live_preview_hub(monkeypatch):
    monkeypatch.delenv("EVILEYE_WS_PREVIEW_MODE", raising=False)
    hub = get_live_preview_hub()
    hub._clients.clear()
    hub._max_clients = 32
    if hub._fanout_task is not None and not hub._fanout_task.done():
        hub._fanout_task.cancel()
    hub._fanout_task = None
    hub._loop = None
    hub._queue = asyncio.Queue(maxsize=256)
    yield


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
