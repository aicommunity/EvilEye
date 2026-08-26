"""Fan-out grid preview JPEGs to WebSocket subscribers.

Per-client latest-wins queues avoid head-of-line blocking: a slow WAN client
cannot stall delivery to everyone else on the shared fan-out loop.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


def _preview_mode() -> str:
    mode = (os.getenv("EVILEYE_WS_PREVIEW_MODE", "binary") or "binary").strip().lower()
    return mode if mode in {"binary", "notify"} else "binary"


def _send_timeout_sec() -> float:
    try:
        return max(0.2, float(os.getenv("EVILEYE_WS_PREVIEW_SEND_TIMEOUT_SEC", "2.0") or 2.0))
    except Exception:
        return 2.0


@dataclass
class LivePreviewClient:
    websocket: WebSocket
    run_id: int
    source_ids: set[int] = field(default_factory=set)
    last_etag: dict[int, str] = field(default_factory=dict)
    # source_id -> (header, payload_or_None for notify mode); latest-wins.
    pending: dict[int, tuple[dict[str, Any], bytes | None]] = field(default_factory=dict)
    send_event: Optional[asyncio.Event] = None
    sender_task: Optional[asyncio.Task] = None
    closed: bool = False
    send_timeouts: int = 0
    replaced_pending: int = 0


class LivePreviewHub:
    def __init__(self) -> None:
        self._clients: list[LivePreviewClient] = []
        self._max_clients = max(1, int(os.getenv("EVILEYE_MAX_LIVE_WS_CLIENTS", "32") or 32))
        self._queue: asyncio.Queue[tuple[str, bytes, dict[str, Any]]] = asyncio.Queue(maxsize=256)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._fanout_task: Optional[asyncio.Task] = None
        self._demand_callback = None
        self._stats = {
            "clients": 0,
            "bytes_sent": 0,
            "messages": 0,
            "dropped": 0,
            "client_timeouts": 0,
            "client_replaced": 0,
            "clients_kicked": 0,
        }

    def set_demand_callback(self, callback) -> None:
        """Optional callback(run_id: int) to refresh grid demand while clients are fed."""
        self._demand_callback = callback

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._fanout_task is not None and not self._fanout_task.done():
            if self._loop is loop:
                return
            self._fanout_task.cancel()
        # Queue is bound to the creating loop; rebuild when the loop changes.
        if self._loop is not loop:
            self._queue = asyncio.Queue(maxsize=256)
        self._loop = loop
        self._fanout_task = loop.create_task(self._fanout_loop())

    async def stop(self) -> None:
        if self._fanout_task is not None:
            self._fanout_task.cancel()
            try:
                await self._fanout_task
            except asyncio.CancelledError:
                pass
            self._fanout_task = None
        for client in list(self._clients):
            self.unregister(client)

    def stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "clients": len(self._clients),
            "max_clients": self._max_clients,
            "mode": _preview_mode(),
            "send_timeout_sec": _send_timeout_sec(),
        }

    async def register(self, websocket: WebSocket, run_id: int) -> LivePreviewClient | None:
        if len(self._clients) >= self._max_clients:
            return None
        client = LivePreviewClient(websocket=websocket, run_id=run_id)
        client.send_event = asyncio.Event()
        loop = self._loop or asyncio.get_running_loop()
        client.sender_task = loop.create_task(self._client_sender(client))
        self._clients.append(client)
        return client

    def unregister(self, client: LivePreviewClient) -> None:
        client.closed = True
        if client.send_event is not None:
            client.send_event.set()
        task = client.sender_task
        if task is not None and not task.done():
            task.cancel()
        client.sender_task = None
        client.pending.clear()
        self._clients = [c for c in self._clients if c is not client]

    def on_broker_publish(self, pipeline_id: str, payload: bytes, metadata: dict[str, Any]) -> None:
        if not payload or ":" not in pipeline_id:
            return
        # Split-editor full frames are not shown on the Live grid WS.
        if ":full:" in pipeline_id:
            return
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        try:
            loop.call_soon_threadsafe(self._enqueue_publish, pipeline_id, payload, dict(metadata or {}))
        except Exception:
            self._stats["dropped"] += 1

    def _enqueue_publish(self, pipeline_id: str, payload: bytes, metadata: dict[str, Any]) -> None:
        try:
            self._queue.put_nowait((pipeline_id, payload, metadata))
        except asyncio.QueueFull:
            self._stats["dropped"] += 1

    def _enqueue_client_frame(
        self,
        client: LivePreviewClient,
        source_id: int,
        header: dict[str, Any],
        payload: bytes | None,
        etag: str,
    ) -> None:
        if client.closed:
            return
        if source_id in client.pending:
            client.replaced_pending += 1
            self._stats["client_replaced"] += 1
        if etag:
            client.last_etag[source_id] = etag
        client.pending[source_id] = (header, payload)
        if client.send_event is not None:
            client.send_event.set()

    async def _client_sender(self, client: LivePreviewClient) -> None:
        timeout = _send_timeout_sec()
        try:
            while not client.closed:
                if client.send_event is None:
                    return
                await client.send_event.wait()
                if client.closed:
                    return
                client.send_event.clear()
                while client.pending and not client.closed:
                    batch = dict(client.pending)
                    client.pending.clear()
                    for _source_id, (header, payload) in batch.items():
                        try:
                            await asyncio.wait_for(client.websocket.send_json(header), timeout=timeout)
                            if payload is not None:
                                await asyncio.wait_for(
                                    client.websocket.send_bytes(payload),
                                    timeout=timeout,
                                )
                                self._stats["bytes_sent"] += len(payload)
                            self._stats["messages"] += 1
                        except asyncio.TimeoutError:
                            client.send_timeouts += 1
                            self._stats["client_timeouts"] += 1
                            self._stats["clients_kicked"] += 1
                            logger.warning(
                                "live preview client send timeout (run_id=%s timeouts=%s); unregistering",
                                client.run_id,
                                client.send_timeouts,
                            )
                            self.unregister(client)
                            return
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            self.unregister(client)
                            return
        except asyncio.CancelledError:
            return

    async def _fanout_loop(self) -> None:
        while True:
            pipeline_id, payload, metadata = await self._queue.get()
            try:
                run_id_str, source_id_str = pipeline_id.split(":", 1)
                run_id = int(run_id_str)
                source_id = int(source_id_str)
            except Exception:
                continue
            etag = str(metadata.get("etag") or "")
            ts = metadata.get("ts") or metadata.get("timestamp")
            mode = _preview_mode()
            if mode == "notify":
                header = {
                    "type": "preview_notify",
                    "source_id": source_id,
                    "ts": ts,
                    "etag": etag,
                    "content_type": "image/jpeg",
                }
                wire_payload: bytes | None = None
            else:
                header = {
                    "type": "preview",
                    "source_id": source_id,
                    "ts": ts,
                    "etag": etag,
                    "content_type": "image/jpeg",
                    "byte_length": len(payload),
                }
                wire_payload = payload
            delivered = False
            for client in list(self._clients):
                if client.closed or client.run_id != run_id:
                    continue
                if client.source_ids and source_id not in client.source_ids:
                    continue
                if etag and client.last_etag.get(source_id) == etag:
                    continue
                self._enqueue_client_frame(client, source_id, header, wire_payload, etag)
                delivered = True
            if delivered and self._demand_callback is not None:
                try:
                    self._demand_callback(run_id)
                except Exception:
                    pass

    def set_client_sources(self, client: LivePreviewClient, source_ids: list[int]) -> None:
        client.source_ids = {int(s) for s in source_ids}
        client.last_etag.clear()


_hub: Optional[LivePreviewHub] = None


def get_live_preview_hub() -> LivePreviewHub:
    global _hub
    if _hub is None:
        _hub = LivePreviewHub()
    return _hub
