import threading
import time

import pytest

import evileye.api.core.server_state as server_state


@pytest.fixture(autouse=True)
def reset_state_caches(monkeypatch: pytest.MonkeyPatch):
    # Keep TTL deterministic for tests; individual tests can override it.
    monkeypatch.setattr(server_state, "_STATE_CACHE_TTL_SEC", 2.0)
    monkeypatch.setattr(server_state, "_STATE_STALE_WHILE_REFRESH_TTL_SEC", 30.0)

    with server_state._camera_summaries_cache_lock:
        server_state._camera_summaries_cache.clear()

    with server_state._overview_cache_lock:
        server_state._overview_cache.value = None
        server_state._overview_cache.expires_at = 0.0
        server_state._overview_cache.stale_expires_at = 0.0
        server_state._overview_cache.computing = False
        server_state._overview_cache.inflight_event = None

    with server_state._current_run_cache_lock:
        server_state._current_run_cache.value = None
        server_state._current_run_cache.expires_at = 0.0
        server_state._current_run_cache.stale_expires_at = 0.0
        server_state._current_run_cache.computing = False
        server_state._current_run_cache.inflight_event = None

    with server_state._active_run_summaries_cache_lock:
        server_state._active_run_summaries_cache.value = None
        server_state._active_run_summaries_cache.expires_at = 0.0
        server_state._active_run_summaries_cache.stale_expires_at = 0.0
        server_state._active_run_summaries_cache.computing = False
        server_state._active_run_summaries_cache.inflight_event = None

    yield


def test_list_camera_summaries_ttl_cache_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server_state, "_STATE_CACHE_TTL_SEC", 10.0)

    calls = {"n": 0}

    fake_run = {
        "id": 1,
        "state": "running",
        "pipeline_class": "PipelineSurveillance",
        "name": "run1",
        "alive": True,
        "sources": [
            {
                "source_id": 0,
                "source_name": "Cam1",
                "source_type": "ip",
                "address": "rtsp://x/y",
            }
        ],
    }

    def fake_runs_for_camera_summaries(scope, *, discover=False):
        calls["n"] += 1
        assert scope == "current"
        return [fake_run]

    def fake_camera_health(run, source_id, *, stale_sec=2.0):
        assert run is fake_run or run.get("id") == 1
        return True, 0.5, True, False

    monkeypatch.setattr(server_state, "_runs_for_camera_summaries", fake_runs_for_camera_summaries)
    monkeypatch.setattr(server_state, "_camera_health", fake_camera_health)

    r1 = server_state.list_camera_summaries(scope="current")
    r2 = server_state.list_camera_summaries(scope="current")

    assert calls["n"] == 1
    assert r1 == r2


def test_list_camera_summaries_returns_stale_while_inflight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server_state, "_STATE_CACHE_TTL_SEC", 0.01)
    monkeypatch.setattr(server_state, "_STATE_STALE_WHILE_REFRESH_TTL_SEC", 0.01)

    calls = {"n": 0}
    compute_started = threading.Event()
    release = threading.Event()

    fake_run = {
        "id": 1,
        "state": "running",
        "pipeline_class": "PipelineSurveillance",
        "name": "run1",
        "alive": True,
        "sources": [
            {
                "source_id": 0,
                "source_name": "Cam1",
                "source_type": "ip",
                "address": "rtsp://x/y",
            }
        ],
    }

    def fake_runs_for_camera_summaries(scope, *, discover=False):
        calls["n"] += 1
        # Second computation is intentionally blocked to keep item.computing=True.
        if calls["n"] == 2:
            compute_started.set()
            release.wait(timeout=2.0)
        return [fake_run]

    def fake_camera_health(run, source_id, *, stale_sec=2.0):
        return True, 0.5, True, False

    monkeypatch.setattr(server_state, "_runs_for_camera_summaries", fake_runs_for_camera_summaries)
    monkeypatch.setattr(server_state, "_camera_health", fake_camera_health)

    first = server_state.list_camera_summaries(scope="current")
    assert calls["n"] == 1

    # Expire both fresh and stale so next call is a sync miss that can block.
    time.sleep(0.02)

    t = threading.Thread(target=server_state.list_camera_summaries, kwargs={"scope": "current"})
    t.start()
    assert compute_started.wait(timeout=1.0)

    # While inflight recompute is ongoing, followers wait briefly then get prior value.
    stale = server_state.list_camera_summaries(scope="current")
    assert stale == first
    assert calls["n"] == 2  # No third expensive call started.

    release.set()
    t.join(timeout=2.0)
    assert t.is_alive() is False


def test_list_camera_summaries_swr_refreshes_in_background(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server_state, "_STATE_CACHE_TTL_SEC", 0.05)
    monkeypatch.setattr(server_state, "_STATE_STALE_WHILE_REFRESH_TTL_SEC", 5.0)

    calls = {"n": 0}
    release = threading.Event()
    started = threading.Event()

    fake_run = {
        "id": 1,
        "state": "running",
        "pipeline_class": "PipelineSurveillance",
        "name": "run1",
        "alive": True,
        "sources": [{"source_id": 0, "source_name": "Cam1", "source_type": "ip", "address": "rtsp://x"}],
    }

    def fake_runs(scope, *, discover=False):
        calls["n"] += 1
        if calls["n"] >= 2:
            started.set()
            release.wait(timeout=2.0)
            return [{**fake_run, "name": "run1-refreshed"}]
        return [fake_run]

    monkeypatch.setattr(server_state, "_runs_for_camera_summaries", fake_runs)
    monkeypatch.setattr(server_state, "_camera_health", lambda *a, **k: (True, 0.1, True, False))

    first = server_state.list_camera_summaries(scope="current")
    assert first[0]["run_name"] == "run1"
    time.sleep(0.06)  # expire fresh, keep stale

    t0 = time.perf_counter()
    second = server_state.list_camera_summaries(scope="current")
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert second == first  # immediate stale
    assert elapsed_ms < 100
    assert started.wait(timeout=1.0)
    release.set()

    deadline = time.time() + 1.0
    third = second
    while time.time() < deadline:
        third = server_state.list_camera_summaries(scope="current")
        if third and third[0].get("run_name") == "run1-refreshed":
            break
        time.sleep(0.01)
    assert third[0]["run_name"] == "run1-refreshed"
    assert calls["n"] == 2


def test_list_camera_summaries_uses_slim_path_not_full_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"full": 0, "slim": 0}

    def boom_get_current():
        calls["full"] += 1
        raise AssertionError("get_current_run_summary must not be used for cameras")

    fake_run = {
        "id": 7,
        "state": "running",
        "pipeline_class": "PipelineSurveillance",
        "name": "run7",
        "alive": True,
        "sources": [{"source_id": 0, "source_name": "Cam1", "source_type": "ip", "address": "rtsp://x"}],
        "runtime_snapshot": {"sources": [{"source_ids": [0], "is_working": True}]},
    }

    def fake_runs(scope, *, discover=False):
        calls["slim"] += 1
        return [fake_run]

    monkeypatch.setattr(server_state, "get_current_run_summary", boom_get_current)
    monkeypatch.setattr(server_state, "_runs_for_camera_summaries", fake_runs)
    monkeypatch.setattr(server_state, "_camera_health", lambda *a, **k: (True, 0.1, True, False))

    items = server_state.list_camera_summaries(scope="current")
    assert calls["full"] == 0
    assert calls["slim"] == 1
    assert items[0]["run_id"] == 7
    assert items[0]["source_name"] == "Cam1"


def test_build_overview_ttl_cache_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server_state, "_STATE_CACHE_TTL_SEC", 10.0)

    calls = {"n": 0}

    def fake_get_current_run_summary():
        return {
            "id": 1,
            "state": "running",
            "pipeline_class": "PipelineSurveillance",
            "name": "run1",
            "alive": True,
            "sources": [
                {
                    "source_id": 0,
                    "source_name": "Cam1",
                    "source_type": "ip",
                    "address": "rtsp://x/y",
                }
            ],
        }

    def fake_list_active_run_summaries():
        return [{"id": 1, "state": "running"}]

    def fake_camera_health(run, source_id, *, stale_sec: float = 2.0):
        calls["n"] += 1
        return True, 0.5, True, False

    monkeypatch.setattr(server_state, "get_current_run_summary", fake_get_current_run_summary)
    monkeypatch.setattr(server_state, "list_active_run_summaries", fake_list_active_run_summaries)
    monkeypatch.setattr(server_state, "_camera_health", fake_camera_health)
    monkeypatch.setattr(server_state, "_log_files", lambda: [])
    monkeypatch.setattr(server_state, "_journal_stats", lambda: {"available": True})
    monkeypatch.setattr(server_state, "_read_log_tail", lambda *args, **kwargs: [])

    o1 = server_state.build_overview()
    o2 = server_state.build_overview()

    assert calls["n"] == 1
    assert o1["server"]["current_run_state"] == "running"
    assert o1 == o2


def test_camera_summaries_follower_wait_does_not_block_compute(monkeypatch: pytest.MonkeyPatch) -> None:
    """Followers must wait outside the cache lock, otherwise compute never finishes and UI gets []."""
    started = threading.Event()
    release = threading.Event()
    results: list[list] = []

    fake_run = {
        "id": 1,
        "state": "running",
        "pipeline_class": "PipelineSurveillance",
        "name": "run1",
        "alive": True,
        "sources": [{"source_id": 0, "source_name": "Cam1", "source_type": "ip", "address": "rtsp://x"}],
    }

    def fake_runs(scope, *, discover=False):
        started.set()
        release.wait(timeout=2.0)
        return [fake_run]

    monkeypatch.setattr(server_state, "_runs_for_camera_summaries", fake_runs)
    monkeypatch.setattr(server_state, "_camera_health", lambda *a, **k: (True, 0.5, True, False))

    def _call():
        results.append(server_state.list_camera_summaries(scope="current"))

    first = threading.Thread(target=_call)
    first.start()
    assert started.wait(timeout=1.0)
    follower = threading.Thread(target=_call)
    follower.start()
    time.sleep(0.05)
    release.set()
    first.join(timeout=2.0)
    follower.join(timeout=2.0)
    assert first.is_alive() is False
    assert follower.is_alive() is False
    assert len(results) == 2
    assert all(row and row[0]["source_name"] == "Cam1" for row in results)

