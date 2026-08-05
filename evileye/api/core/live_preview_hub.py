"""Fan-out grid preview JPEGs to WebSocket subscribers."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import WebSocket


@dataclass
class LivePreviewClient:
    websocket: WebSocket
    run_id: int
    source_ids: set[int] = field(default_factory=set)
    last_etag: dict[int, str] = field(default_factory=dict)


class LivePreviewHub:
    def __init__(self) -> None:
        self._clients: list[LivePreviewClient] = []
        self._max_clients = max(1, int(os.getenv("EVILEYE_MAX_LIVE_WS_CLIENTS", "32") or 32))
        self._queue: asyncio.Queue[tuple[str, bytes, dict[str, Any]]] = asyncio.Queue(maxsize=256)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._fanout_task: Optional[asyncio.Task] = None
        self._stats = {"clients": 0, "bytes_sent": 0, "messages": 0, "dropped": 0}

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._fanout_task is not None and not self._fanout_task.done():
            if self._loop is loop:
                return
            self._fanout_task.cancel()
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

    def stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "clients": len(self._clients),
            "max_clients": self._max_clients,
        }

    async def register(self, websocket: WebSocket, run_id: int) -> LivePreviewClient | None:
        if len(self._clients) >= self._max_clients:
            return None
        client = LivePreviewClient(websocket=websocket, run_id=run_id)
        self._clients.append(client)
        return client

    def unregister(self, client: LivePreviewClient) -> None:
        self._clients = [c for c in self._clients if c is not client]

    def on_broker_publish(self, pipeline_id: str, payload: bytes, metadata: dict[str, Any]) -> None:
        if not payload or ":" not in pipeline_id:
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
            header = {
                "type": "preview",
                "source_id": source_id,
                "ts": ts,
                "etag": etag,
                "content_type": "image/jpeg",
                "byte_length": len(payload),
            }
            for client in list(self._clients):
                if client.run_id != run_id:
                    continue
                if client.source_ids and source_id not in client.source_ids:
                    continue
                if etag and client.last_etag.get(source_id) == etag:
                    continue
                client.last_etag[source_id] = etag
                try:
                    await client.websocket.send_json(header)
                    await client.websocket.send_bytes(payload)
                    self._stats["messages"] += 1
                    self._stats["bytes_sent"] += len(payload)
                except Exception:
                    self.unregister(client)

    def set_client_sources(self, client: LivePreviewClient, source_ids: list[int]) -> None:
        client.source_ids = {int(s) for s in source_ids}
        client.last_etag.clear()


_hub: Optional[LivePreviewHub] = None


def get_live_preview_hub() -> LivePreviewHub:
    global _hub
    if _hub is None:
        _hub = LivePreviewHub()
    return _hub
