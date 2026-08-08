import json
from pathlib import Path

import evileye.api.core.runtime_registry as rr


def test_save_runtime_record_atomic_and_loadable(tmp_path, monkeypatch):
    monkeypatch.setattr(rr, "RUNTIME_ROOT", tmp_path)
    monkeypatch.setattr(rr, "REGISTRY_DIR", tmp_path / "pipelines")
    monkeypatch.setattr(rr, "SNAPSHOT_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(rr, "LOCK_FILE", tmp_path / ".lock")
    rr._corrupt_record_logged.clear()

    saved = rr.save_runtime_record(
        {
            "id": 42,
            "pid": None,
            "state": "stopped",
            "name": "test",
        }
    )
    assert saved["id"] == 42
    path = rr._record_path(42)
    assert path.exists()
    # No leftover temp files
    leftovers = list((tmp_path / "pipelines").glob(".*.tmp"))
    assert leftovers == []

    loaded = rr.load_runtime_record(42, refresh_state=False)
    assert loaded is not None
    assert loaded["name"] == "test"


def test_load_runtime_record_skips_corrupt_without_spam(tmp_path, monkeypatch):
    monkeypatch.setattr(rr, "RUNTIME_ROOT", tmp_path)
    monkeypatch.setattr(rr, "REGISTRY_DIR", tmp_path / "pipelines")
    monkeypatch.setattr(rr, "SNAPSHOT_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(rr, "LOCK_FILE", tmp_path / ".lock")
    rr._corrupt_record_logged.clear()

    path = rr._record_path(7)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"id": 7}\n{"extra": true}\n', encoding="utf-8")

    assert rr.load_runtime_record(7, refresh_state=False) is None
    assert 7 in rr._corrupt_record_logged
    assert not path.exists()

    # Second read of missing file stays quiet (set already has rid)
    assert rr.load_runtime_record(7, refresh_state=False) is None
