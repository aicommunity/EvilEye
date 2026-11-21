"""Reaudit R07: playback slot wait included in route deadline."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from evileye.api.routes import playback as playback_routes


def test_playback_queue_deadline_returns_cached_or_503(monkeypatch):
    monkeypatch.setattr(playback_routes, "playback_route_timeout_sec", lambda: 0.05)

    async def _main():
        sem = asyncio.Semaphore(0)
        cached = {"ok": True}
        result = await playback_routes._to_thread_with_timeout_or_cached(
            lambda: {"fresh": True},
            lambda: cached,
            err_detail="playback timeout",
            slot_sem=sem,
        )
        assert result == cached
        with pytest.raises(HTTPException) as exc:
            await playback_routes._to_thread_with_timeout_or_cached(
                lambda: {"fresh": True},
                lambda: None,
                err_detail="playback timeout",
                slot_sem=sem,
            )
        assert exc.value.status_code == 503

    asyncio.run(_main())
