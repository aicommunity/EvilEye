"""Regression: cancelled /playback/media must release the inflight slot."""
from __future__ import annotations

import asyncio
import time


def test_media_inflight_released_when_resolve_cancelled(monkeypatch, tmp_path):
    import evileye.api.routes.playback as pb
    from evileye.api.core import playback_service as svc

    media = tmp_path / "Cam1_20260913_000000_0_00000.mp4"
    media.write_bytes(b"\x00" * 1024)

    with pb._media_inflight_lock:
        pb._media_inflight = 0

    started = asyncio.Event()

    def slow_resolve(_path: str):
        # Signal from worker thread; Event.set is thread-safe.
        started.set()
        time.sleep(30)
        return media

    monkeypatch.setattr(svc, "resolve_media_path", slow_resolve)
    monkeypatch.setenv("EVILEYE_MAX_PLAYBACK_MEDIA_CLIENTS", "96")

    class _Access:
        unrestricted = True
        allowed_names: set[str] = set()

    monkeypatch.setattr(pb, "resolve_camera_access", lambda _req: _Access())

    async def _run() -> None:
        task = asyncio.create_task(
            pb.playback_media(object(), path=str(media))  # type: ignore[arg-type]
        )
        await asyncio.wait_for(started.wait(), timeout=2.0)
        assert pb.media_inflight_count() >= 1
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert pb.media_inflight_count() == 0

    asyncio.run(_run())
