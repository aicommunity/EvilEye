from datetime import datetime, timedelta
from pathlib import Path

import evileye.api.core.log_service as log_service
import evileye.api.core.runtime_registry as rr


def test_allocate_log_session_id_avoids_collision(tmp_path):
    base = datetime.now().strftime("%Y%m%d_%H%M%S")
    (tmp_path / f"{base}_evileye_main.log").write_text("x", encoding="utf-8")
    sid = log_service.allocate_log_session_id(logs_dir=tmp_path)
    assert sid != base
    assert sid.startswith(base)
    assert not (tmp_path / f"{sid}_evileye_main.log").exists()


def test_resolve_run_log_files_exact(tmp_path):
    sid = "20260101_120000"
    (tmp_path / f"{sid}_evileye_main.log").write_text("main", encoding="utf-8")
    (tmp_path / f"{sid}_evileye_errors.log").write_text("err", encoding="utf-8")
    out = log_service.resolve_run_log_files({"log_session_id": sid}, logs_dir=tmp_path)
    assert out["log_match"] == "exact"
    assert out["log_session_id"] == sid
    assert out["log_files"]["main"] == f"{sid}_evileye_main.log"
    assert out["log_files"]["errors"] == f"{sid}_evileye_errors.log"


def test_resolve_run_log_files_exact_without_file_still_links_main(tmp_path):
    sid = "20260101_130000"
    out = log_service.resolve_run_log_files({"log_session_id": sid}, logs_dir=tmp_path)
    assert out["log_match"] == "exact"
    assert out["log_files"]["main"] == f"{sid}_evileye_main.log"


def test_resolve_run_log_files_heuristic(tmp_path):
    started = datetime(2026, 1, 1, 12, 0, 5)
    sid = "20260101_120000"
    (tmp_path / f"{sid}_evileye_main.log").write_text("main", encoding="utf-8")
    out = log_service.resolve_run_log_files(
        {"started_at": started.timestamp()},
        logs_dir=tmp_path,
        max_delta_sec=120,
    )
    assert out["log_match"] == "heuristic"
    assert out["log_session_id"] == sid
    assert out["log_files"]["main"] == f"{sid}_evileye_main.log"


def test_resolve_run_log_files_heuristic_outside_window(tmp_path):
    started = datetime(2026, 1, 1, 12, 0, 0)
    far = started - timedelta(minutes=10)
    sid = far.strftime("%Y%m%d_%H%M%S")
    (tmp_path / f"{sid}_evileye_main.log").write_text("main", encoding="utf-8")
    out = log_service.resolve_run_log_files(
        {"started_at": started.timestamp()},
        logs_dir=tmp_path,
        max_delta_sec=120,
    )
    assert out["log_match"] == "none"
    assert out["log_session_id"] is None


def test_resolve_run_log_files_none_without_started_at(tmp_path):
    out = log_service.resolve_run_log_files({}, logs_dir=tmp_path)
    assert out["log_match"] == "none"


def test_register_runtime_persists_log_session_id(tmp_path, monkeypatch):
    monkeypatch.setattr(rr, "RUNTIME_ROOT", tmp_path)
    monkeypatch.setattr(rr, "REGISTRY_DIR", tmp_path / "pipelines")
    monkeypatch.setattr(rr, "SNAPSHOT_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(rr, "LOCK_FILE", tmp_path / ".lock")

    saved = rr.register_runtime(
        rid=9,
        pid=1234,
        config_path="/tmp/foo.json",
        name="foo",
        frame_dir=None,
        source="web",
        managed=True,
        state="running",
        session_id="abc123",
        log_session_id="20260101_120000",
    )
    assert saved["log_session_id"] == "20260101_120000"
    loaded = rr.load_runtime_record(9, refresh_state=False)
    assert loaded is not None
    assert loaded["log_session_id"] == "20260101_120000"
    # Merge keeps log_session_id when omitted
    rr.register_runtime(
        rid=9,
        pid=1234,
        config_path="/tmp/foo.json",
        name="foo",
        frame_dir=None,
        source="process",
        state="running",
    )
    loaded2 = rr.load_runtime_record(9, refresh_state=False)
    assert loaded2["log_session_id"] == "20260101_120000"


def test_run_summary_includes_config_name_and_logs(tmp_path, monkeypatch):
    import evileye.api.core.server_state as ss

    monkeypatch.setattr(rr, "RUNTIME_ROOT", tmp_path)
    monkeypatch.setattr(rr, "REGISTRY_DIR", tmp_path / "pipelines")
    monkeypatch.setattr(rr, "SNAPSHOT_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(rr, "LOCK_FILE", tmp_path / ".lock")

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    sid = "20260101_140000"
    (logs_dir / f"{sid}_evileye_main.log").write_text("ok", encoding="utf-8")

    # resolve_run_log_files uses Path("logs") by default; monkeypatch via cwd
    monkeypatch.chdir(tmp_path)

    rr.register_runtime(
        rid=3,
        pid=1,
        config_path=str(tmp_path / "configs" / "demo.json"),
        name="demo",
        frame_dir=None,
        source="web",
        state="stopped",
        log_session_id=sid,
    )
    summary = ss._run_summary(rr.load_runtime_record(3, refresh_state=False))
    assert summary["config_name"] == "demo.json"
    assert summary["log_session_id"] == sid
    assert summary["log_match"] == "exact"
    assert summary["log_files"]["main"] == f"{sid}_evileye_main.log"


def test_run_summary_storage_mode_from_snapshot(tmp_path, monkeypatch):
    import evileye.api.core.server_state as ss

    monkeypatch.setattr(rr, "RUNTIME_ROOT", tmp_path)
    monkeypatch.setattr(rr, "REGISTRY_DIR", tmp_path / "pipelines")
    monkeypatch.setattr(rr, "SNAPSHOT_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(rr, "LOCK_FILE", tmp_path / ".lock")

    config_path = tmp_path / "configs" / "demo.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        '{"controller": {"use_database": true}, "database": {"image_dir": "EvilEyeData"}}',
        encoding="utf-8",
    )

    rr.register_runtime(
        rid=4,
        pid=1,
        config_path=str(config_path),
        name="demo",
        frame_dir=None,
        source="web",
        state="running",
    )
    rr.save_runtime_snapshot(
        4,
        {
            "config": {
                "controller": {"use_database": False},
                "database": {"image_dir": "EvilEyeData"},
            },
        },
    )

    summary = ss._run_summary(rr.load_runtime_record(4, refresh_state=False))
    assert summary["database_enabled"] is False
    assert summary["storage_mode"] == "json"
