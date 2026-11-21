"""A09/A10: detection ticks and event intervals coverage + signature."""

from __future__ import annotations

import json
import time

from evileye.api.core import playback_timeline_index as idx


def test_detection_ticks_merges_second_camera(tmp_path, monkeypatch):
    date = "2026-08-17"
    meta_dir = tmp_path / "Detections" / date / "Metadata"
    meta_dir.mkdir(parents=True)
    (meta_dir / "objects_found.json").write_text("[]", encoding="utf-8")
    (meta_dir / "objects_lost.json").write_text("[]", encoding="utf-8")
    ticks_path = meta_dir / "detection_ticks.json"
    ticks_path.write_text(
        json.dumps(
            {
                "version": idx.INDEX_VERSION,
                "date": date,
                "built_at": time.time(),
                "source_mtime": idx._file_mtime_sum_safe(meta_dir) if hasattr(idx, "_file_mtime_sum_safe") else 0.0,
                "cameras": ["Cam1"],
                "by_camera": {"Cam1": [[1.0, "found", 1]]},
            }
        ),
        encoding="utf-8",
    )
    # Align source_mtime with objects files so index is "fresh" but incomplete.
    from evileye.api.core import playback_metadata_service as meta

    source_mtime = meta._file_mtime_sum(
        meta_dir / "objects_found.json",
        meta_dir / "objects_lost.json",
    )
    ticks_path.write_text(
        json.dumps(
            {
                "version": idx.INDEX_VERSION,
                "date": date,
                "built_at": time.time(),
                "source_mtime": source_mtime,
                "cameras": ["Cam1"],
                "by_camera": {"Cam1": [[1.0, "found", 1]]},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(meta, "_load_params_for_run", lambda _run_id=None: {})
    monkeypatch.setattr(meta, "_playback_data_dir", lambda _params: tmp_path)

    def fake_day(**kwargs):
        cams = kwargs.get("cameras") or []
        return {c: [{"ts": 2.0, "kind": "found", "object_id": 2}] for c in cams}

    monkeypatch.setattr(meta, "_load_day_index_by_camera", fake_day)

    out = idx.ensure_detection_ticks(date_folder=date, cameras=["Cam1", "Cam2"])
    assert out["Cam1"][0]["ts"] == 1.0
    assert out["Cam2"][0]["ts"] == 2.0
    disk = json.loads(ticks_path.read_text(encoding="utf-8"))
    assert "Cam1" in disk["by_camera"] and "Cam2" in disk["by_camera"]


def test_event_intervals_signature_excludes_self(tmp_path, monkeypatch):
    date = "2026-08-19"
    events_dir = tmp_path / "Events" / date / "Metadata"
    events_dir.mkdir(parents=True)
    (events_dir / "zone_events_entered.json").write_text("[]", encoding="utf-8")
    (events_dir / "zone_events_left.json").write_text("[]", encoding="utf-8")

    monkeypatch.setattr(
        "evileye.api.core.playback_service.data_dir",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "evileye.api.core.playback_service.load_event_intervals",
        lambda *a, **k: [
            {"camera": "Cam1", "start_ts": 1.0, "end_ts": 2.0, "zone_name": "Z"},
            {"camera": "Cam2", "start_ts": 3.0, "end_ts": 4.0, "zone_name": "Z"},
        ],
    )

    first = idx.ensure_event_intervals(date_folder=date, cameras=["Cam1"])
    assert len(first) == 1 and first[0]["camera"] == "Cam1"
    sig_before = idx._dir_mtime_sig(
        events_dir, ("*.json",), exclude_names=idx._GENERATED_INDEX_NAMES
    )
    # Touch generated file mtime
    index_path = events_dir / "event_intervals.json"
    assert index_path.is_file()
    time.sleep(0.05)
    index_path.touch()
    sig_after = idx._dir_mtime_sig(
        events_dir, ("*.json",), exclude_names=idx._GENERATED_INDEX_NAMES
    )
    assert abs(sig_before - sig_after) < 1e-6

    second = idx.ensure_event_intervals(date_folder=date, cameras=["Cam2"])
    assert any(it["camera"] == "Cam2" for it in second)
    # Full file still has both cameras after rebuild/filter
    disk = json.loads(index_path.read_text(encoding="utf-8"))
    cams = {it.get("camera") for it in disk.get("items") or []}
    assert "Cam1" in cams and "Cam2" in cams
