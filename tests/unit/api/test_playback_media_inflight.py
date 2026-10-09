"""Regression: cancelled /playback/media must release the inflight slot."""
from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace


def test_media_inflight_released_when_resolve_cancelled(monkeypatch, tmp_path):
    import evileye.api.routes.playback as pb
    media = tmp_path / "Cam1_20260913_000000_0_00000.mp4"
    media.write_bytes(b"\x00" * 1024)

    with pb._media_inflight_lock:
        pb._media_inflight = 0

    started = threading.Event()
    release = threading.Event()

    def slow_resolve(_path: str):
        # Resolver runs in a worker thread, so use a thread-safe event.
        started.set()
        release.wait(timeout=2.0)
        return media

    class _SlowResolver:
        def __init__(self, _data_dir):
            pass

        def resolve(self, _access, _path):
            resolved = slow_resolve(_path)
            return SimpleNamespace(path=resolved)

    monkeypatch.setattr(pb, "ArchiveMediaResolver", _SlowResolver)
    monkeypatch.setattr(pb.svc, "data_dir", lambda: tmp_path)
    monkeypatch.setenv("EVILEYE_MAX_PLAYBACK_MEDIA_CLIENTS", "96")

    class _Access:
        unrestricted = True
        allowed_names: set[str] = set()

    monkeypatch.setattr(pb, "resolve_camera_access", lambda _req: _Access())

    async def _run() -> None:
        task = asyncio.create_task(
            pb.playback_media(object(), path=str(media))  # type: ignore[arg-type]
        )
        assert await asyncio.to_thread(started.wait, 2.0)
        assert pb.media_inflight_count() >= 1
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert pb.media_inflight_count() == 0
        release.set()

    asyncio.run(_run())
