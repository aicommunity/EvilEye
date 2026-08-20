import json
import os
import time

import evileye.api.core.runtime_registry as rr


def _patch_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(rr, "RUNTIME_ROOT", tmp_path)
    monkeypatch.setattr(rr, "REGISTRY_DIR", tmp_path / "pipelines")
    monkeypatch.setattr(rr, "SNAPSHOT_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(rr, "LOCK_FILE", tmp_path / ".lock")
    rr._corrupt_record_logged.clear()
    rr._last_discover_ts = 0.0
    with rr._stubs_cache_lock:
        rr._stubs_cache_value = None
        rr._stubs_cache_ts = 0.0
    try:
        from evileye.api.core import server_state as ss

        with ss._current_run_cache_lock:
            ss._current_run_cache.value = None
            ss._current_run_cache.expires_at = 0.0
            ss._current_run_cache.stale_expires_at = 0.0
            ss._current_run_cache.computing = False
            ss._current_run_cache.inflight_event = None
        with ss._active_run_summaries_cache_lock:
            ss._active_run_summaries_cache.value = None
            ss._active_run_summaries_cache.expires_at = 0.0
            ss._active_run_summaries_cache.stale_expires_at = 0.0
            ss._active_run_summaries_cache.computing = False
            ss._active_run_summaries_cache.inflight_event = None
        with ss._camera_summaries_cache_lock:
            ss._camera_summaries_cache.clear()
    except Exception:
        pass


def test_prune_keeps_alive_and_recent_stopped(tmp_path, monkeypatch):
    _patch_registry(tmp_path, monkeypatch)
    now = time.time()
    rr.save_runtime_record(
        {"id": 1, "pid": 1, "state": "running", "alive": True, "updated_at": now, "name": "alive"}
    )
    monkeypatch.setattr(rr, "_is_pid_alive", lambda pid: int(pid or 0) == 1)

    for rid in range(2, 12):
        rr.save_runtime_record(
            {
                "id": rid,
                "pid": None,
                "state": "stopped",
                "alive": False,
                "stopped_at": now - rid,
                "updated_at": now - rid,
                "name": f"old-{rid}",
            }
        )

    # Very old stopped
    rr.save_runtime_record(
        {
            "id": 99,
            "pid": None,
            "state": "stopped",
            "alive": False,
            "stopped_at": now - 30 * 86400,
            "updated_at": now - 30 * 86400,
            "name": "ancient",
        }
    )

    pruned = rr.prune_stale_runtime_records(max_stopped_age_sec=7 * 86400, keep_recent_stopped=3, max_total_records=10)
    assert pruned >= 1
    remaining = rr.list_runtime_record_stubs(discover=False)
    assert 1 in remaining
    assert 99 not in remaining
    assert len(remaining) <= 1 + 3


def test_list_runtime_record_stubs_light(tmp_path, monkeypatch):
    _patch_registry(tmp_path, monkeypatch)
    rr.save_runtime_record(
        {"id": 5, "pid": None, "state": "stopped", "name": "x", "config_path": "/tmp/c.json"}
    )
    stubs = rr.list_runtime_record_stubs(discover=False)
    assert 5 in stubs
    assert stubs[5]["config_path"] == "/tmp/c.json"
    assert "runtime_snapshot" not in stubs[5]


def test_get_current_run_summary_hydrates_one(tmp_path, monkeypatch):
    _patch_registry(tmp_path, monkeypatch)
    from evileye.api.core import server_state as ss

    now = time.time()
    for rid in range(1, 21):
        path = rr._record_path(rid)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "id": rid,
                    "pid": None,
                    "state": "stopped",
                    "alive": False,
                    "updated_at": now - rid,
                    "config_path": "",
                    "name": f"r{rid}",
                }
            ),
            encoding="utf-8",
        )
    rr.save_runtime_record(
        {
            "id": 100,
            "pid": 4242,
            "state": "running",
            "alive": True,
            "updated_at": now,
            "config_path": "",
            "name": "current",
        }
    )
    monkeypatch.setattr(rr, "_is_pid_alive", lambda pid: int(pid or 0) == 4242)
    monkeypatch.setattr(ss, "maybe_discover_process_runtimes", lambda force=False: None)
    monkeypatch.setattr(rr, "maybe_discover_process_runtimes", lambda force=False: None)

    class _Mgr:
        def list(self):
            return {}

        def describe(self, rid):
            raise KeyError(rid)

    monkeypatch.setattr(ss, "get_config_run_manager", lambda: _Mgr())

    calls = {"n": 0}
    real = ss._run_summary

    def tracked(record):
        calls["n"] += 1
        return real(record)

    monkeypatch.setattr(ss, "_run_summary", tracked)
    current = ss.get_current_run_summary()
    assert current is not None
    assert current["id"] == 100
    assert calls["n"] == 1


def test_refresh_marks_foreign_pid_stopped(tmp_path, monkeypatch):
    _patch_registry(tmp_path, monkeypatch)
    rr.save_runtime_record(
        {
            "id": 7,
            "pid": 424242,
            "state": "running",
            "alive": True,
            "updated_at": time.time(),
            "name": "foreign",
        }
    )
    monkeypatch.setattr(os, "kill", lambda pid, sig: None)
    monkeypatch.setattr(rr, "_parse_process_cmdline", lambda pid: None)

    record = rr.load_runtime_record(7)
    assert record is not None
    assert record["alive"] is False
    assert record["state"] == "stopped"
    assert record["pid"] is None


def test_skip_unchanged_runtime_snapshot_write(tmp_path, monkeypatch):
    _patch_registry(tmp_path, monkeypatch)
    writes = {"n": 0}
    real_atomic = rr._atomic_write_text

    def tracked(path, text, *, fsync=True):
        writes["n"] += 1
        return real_atomic(path, text, fsync=fsync)

    monkeypatch.setattr(rr, "_atomic_write_text", tracked)
    first = rr.save_runtime_snapshot(42, {"sources": [{"source_ids": [0], "is_working": True}], "config": {"a": 1}})
    assert writes["n"] == 1
    second = rr.update_runtime_snapshot(42, sources=[{"source_ids": [0], "is_working": True}], config={"a": 1})
    assert writes["n"] == 1
    assert second["updated_at"] == first["updated_at"]
    rr.update_runtime_snapshot(42, sources=[{"source_ids": [0], "is_working": False}], config={"a": 1})
    assert writes["n"] == 2


def test_skip_unchanged_runtime_record_write(tmp_path, monkeypatch):
    _patch_registry(tmp_path, monkeypatch)
    monkeypatch.setattr(rr, "_is_pid_alive", lambda pid: False)
    writes = {"n": 0}
    real_atomic = rr._atomic_write_text

    def tracked(path, text, *, fsync=True):
        writes["n"] += 1
        return real_atomic(path, text, fsync=fsync)

    monkeypatch.setattr(rr, "_atomic_write_text", tracked)
    rr.save_runtime_record({"id": 9, "pid": None, "state": "stopped", "alive": False, "name": "x"})
    assert writes["n"] == 1
    rr.save_runtime_record({"id": 9, "pid": None, "state": "stopped", "alive": False, "name": "x"})
    assert writes["n"] == 1
    rr.save_runtime_record({"id": 9, "pid": None, "state": "stopped", "alive": False, "name": "y"})
    assert writes["n"] == 2
