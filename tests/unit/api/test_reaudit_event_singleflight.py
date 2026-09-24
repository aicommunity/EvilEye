"""Reaudit R03: event singleflight must not leak leader camera projection."""

from __future__ import annotations

import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from evileye.api.core import playback_service as svc
from evileye.api.core import playback_timeline_index as idx


def test_event_singleflight_isolates_camera_projection(tmp_path):
    date = "2020-03-01"
    (tmp_path / "Events" / date / "Metadata").mkdir(parents=True)
    started, release = threading.Event(), threading.Event()
    follower_thread: list[int] = []

    def loader(*args, **kwargs):
        started.set()
        assert release.wait(5)
        return [
            {"camera": "Cam1", "start_ts": 1.0, "end_ts": 2.0},
            {"camera": "Cam2", "start_ts": 1.0, "end_ts": 2.0},
        ]

    def follower():
        follower_thread.append(threading.get_ident())
        return idx.ensure_event_intervals(date_folder=date, cameras=["Cam2"])

    with patch.object(svc, "data_dir", return_value=tmp_path), patch.object(
        svc, "load_event_intervals", side_effect=loader
    ):
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(idx.ensure_event_intervals, date_folder=date, cameras=["Cam1"])
            assert started.wait(5)
            b = pool.submit(follower)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                frame = sys._current_frames().get(follower_thread[0]) if follower_thread else None
                waiting = False
                while frame:
                    if frame.f_code.co_name in {"wait", "result", "ensure_event_intervals", "singleflight"}:
                        waiting = True
                        break
                    frame = frame.f_back
                if waiting:
                    break
                time.sleep(0.01)
            release.set()
            leader = a.result(timeout=5)
            follower_items = b.result(timeout=5)

    assert {it["camera"] for it in leader} == {"Cam1"}
    assert {it["camera"] for it in follower_items} == {"Cam2"}
