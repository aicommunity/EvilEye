"""Route timeout helpers and playback stale fallback."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException

from evileye.api.core import playback_timeline_index as idx
from evileye.api.core.route_timeouts import (
    env_timeout_sec,
    playback_route_timeout_sec,
    state_route_timeout_sec,
)
from evileye.api.routes import playback as playback_routes


def test_env_timeout_sec_defaults_and_floor(monkeypatch):
    monkeypatch.delenv("EVILEYE_PLAYBACK_ROUTE_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("EVILEYE_STATE_ROUTE_TIMEOUT_SEC", raising=False)
    assert playback_route_timeout_sec() == 15.0
    assert state_route_timeout_sec() == 8.0

    monkeypatch.setenv("EVILEYE_PLAYBACK_ROUTE_TIMEOUT_SEC", "1")
    assert playback_route_timeout_sec() == 2.0  # floor

    monkeypatch.setenv("EVILEYE_STATE_ROUTE_TIMEOUT_SEC", "12.5")
    assert state_route_timeout_sec() == 12.5

    assert env_timeout_sec("MISSING_ENV", 9.0) == 9.0


def test_read_segment_index_stale_ignores_mtime(tmp_path, monkeypatch):
    date = "2026-08-17"
    streams = tmp_path / "Streams" / date / "Cam1"
    streams.mkdir(parents=True)
    (streams / "Cam1_x.mp4").write_bytes(b"x")
    index_path = streams.parent / "_timeline_segments.json"
    payload = {
        "version": idx.INDEX_VERSION,
        "date": date,
        "built_at": 1.0,
        "source_mtime": 0.0,  # deliberately stale vs real mtime sum
        "by_camera": {
            "Cam1": [
                {
                    "path": str(streams / "Cam1_x.mp4"),
                    "start_ts": 100.0,
                    "end_ts": 200.0,
                    "camera": "Cam1",
                    "playable": True,
                }
            ]
        },
    }
    index_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr("evileye.api.core.playback_service.data_dir", lambda: tmp_path)

    assert idx.read_segment_index_if_fresh(date) is None
    stale = idx.read_segment_index_stale(date)
    assert stale is not None
    assert stale["Cam1"][0]["start_ts"] == 100.0


def test_playback_segments_timeout_serves_stale(tmp_path, monkeypatch):
    date = "2026-08-17"
    streams = tmp_path / "Streams" / date / "Cam1"
    streams.mkdir(parents=True)
    index_path = streams.parent / "_timeline_segments.json"
    index_path.write_text(
        json.dumps(
            {
                "version": idx.INDEX_VERSION,
                "date": date,
                "built_at": 1.0,
                "source_mtime": 0.0,
                "by_camera": {
                    "Cam1": [
                        {
                            "path": "p.mp4",
                            "start_ts": 10.0,
                            "end_ts": 20.0,
                            "camera": "Cam1",
                            "playable": True,
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("evileye.api.core.playback_service.data_dir", lambda: tmp_path)
    monkeypatch.setattr(playback_routes, "playback_route_timeout_sec", lambda: 0.2)
    playback_routes._memory_cache.clear()

    def _slow():
        import time

        time.sleep(2.0)
        return {"Cam1": []}

    monkeypatch.setattr(playback_routes.svc, "load_segments_batch", lambda *a, **k: _slow())

    class _Access:
        unrestricted = True
        allowed_names = set()
        visible_names = None

    class _Req:
        pass

    monkeypatch.setattr(playback_routes, "resolve_camera_access", lambda _r: _Access())
    monkeypatch.setattr(
        playback_routes,
        "_require_cameras",
        lambda access, names, single=False: list(names),
    )

    async def _run():
        return await playback_routes.playback_segments(
            _Req(),
            camera=None,
            cameras="Cam1",
            from_ts=None,
            to_ts=None,
            date=date,
        )

    result = asyncio.run(_run())
    assert result["by_camera"]["Cam1"][0]["start_ts"] == 10.0


def test_playback_timeout_without_cache_raises_503(monkeypatch):
    monkeypatch.setattr(playback_routes, "playback_route_timeout_sec", lambda: 0.15)
    playback_routes._memory_cache.clear()

    def _slow():
        import time

        time.sleep(1.0)
        return []

    async def _run():
        with pytest.raises(HTTPException) as exc:
            await playback_routes._to_thread_with_timeout_or_cached(
                _slow,
                lambda: None,
                err_detail="playback_segments timeout",
            )
        assert exc.value.status_code == 503
        assert exc.value.detail == "playback_segments timeout"

    asyncio.run(_run())
