"""Live grid preview WebSocket hub."""

import pytest

from evileye.api.core.live_preview_hub import get_live_preview_hub


@pytest.fixture(autouse=True)
def reset_live_preview_hub():
    hub = get_live_preview_hub()
    hub._clients.clear()
    if hub._fanout_task is not None and not hub._fanout_task.done():
        hub._fanout_task.cancel()
    hub._fanout_task = None
    hub._loop = None
    while not hub._queue.empty():
        try:
            hub._queue.get_nowait()
        except Exception:
            break
    yield


def test_hub_fanout_subscribed_source():
    import asyncio

    async def _run():
        hub = get_live_preview_hub()
        hub._clients.clear()
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
        assert sent_json[0]["source_id"] == 1
        assert sent_bytes == [b"jpeg-bytes"]

        hub.on_broker_publish("7:2", b"other", {"etag": "e2"})
        await asyncio.sleep(0.1)
        assert len(sent_bytes) == 1

    asyncio.run(_run())


def test_hub_skips_duplicate_etag():
    import asyncio

    async def _run():
        hub = get_live_preview_hub()
        hub._clients.clear()
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
