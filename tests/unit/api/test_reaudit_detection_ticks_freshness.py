"""Reaudit R04: detection ticks rebuild when source_mtime changes."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

from evileye.api.core import playback_metadata_service as meta
from evileye.api.core import playback_timeline_index as idx


def test_detection_ticks_reload_on_source_mtime(tmp_path):
    date = "2020-01-01"
    meta_dir = tmp_path / "Detections" / date / "Metadata"
    meta_dir.mkdir(parents=True)
    source = meta_dir / "objects_found.json"
    source.write_text("[]", encoding="utf-8")
    (meta_dir / "objects_lost.json").write_text("[]", encoding="utf-8")
    rows = [{"ts": 1.0, "kind": "found", "object_id": 1}]

    with patch.object(meta, "_load_params_for_run", return_value={}), patch.object(
        meta, "_playback_data_dir", return_value=tmp_path
    ), patch.object(
        meta,
        "_load_day_index_by_camera",
        side_effect=lambda **kw: {"Cam1": list(rows)},
    ) as loader:
        first = idx._rebuild_detection_ticks(date_folder=date, cameras=["Cam1"])
        assert len(first["Cam1"]) == 1
        rows.append({"ts": 2.0, "kind": "found", "object_id": 2})
        st = source.stat()
        os.utime(source, (st.st_atime, st.st_mtime + 10))
        second = idx._rebuild_detection_ticks(date_folder=date, cameras=["Cam1"])
        disk = json.loads((meta_dir / "detection_ticks.json").read_text())
        current_sig = meta._file_mtime_sum(source, meta_dir / "objects_lost.json")

    assert len(second["Cam1"]) == 2
    assert loader.call_count >= 2
    assert disk["source_mtime"] == current_sig
