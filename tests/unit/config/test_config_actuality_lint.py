"""Lint config JSON files for actuality (server/record/GST/scheduled_restart)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SAMPLES = REPO / "evileye" / "samples_configs"
CONFIGS = REPO / "configs"

PARTIAL = {
    "kpi_gate_profile.json",
    "string.json",
    "preprocessing_pipeline.json",
    "example_attributes_config.json",
    "example_attributes_config_clean.json",
    "example_class_mapping.json",
    "example_classes_by_names.json",
    "example_classes_system.json",
    "capture_detection.json",
    "capture_subtraction.json",
    "source_only_test.json",
    "minimal_test.json",
    "test_capture_memory.json",
}


def _pipeline_json_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in sorted(root.glob("*.json")):
        if path.name in PARTIAL:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "pipeline" in data:
            out.append(path)
    return out


def _assert_common(path: Path, data: dict, *, require_preview_encoder: bool) -> None:
    assert isinstance(data.get("server"), dict), f"{path}: missing server"
    assert isinstance(data.get("record"), dict), f"{path}: missing record"
    ctrl = data.get("controller")
    assert isinstance(ctrl, dict), f"{path}: missing controller"
    assert isinstance(ctrl.get("scheduled_restart"), dict), f"{path}: missing scheduled_restart"
    if require_preview_encoder:
        assert data["server"].get("preview_encoder"), f"{path}: missing preview_encoder"
    sources = (data.get("pipeline") or {}).get("sources") or []
    for src in sources:
        if not isinstance(src, dict):
            continue
        if src.get("type") == "VideoCaptureGStreamer":
            assert src.get("apiPreference") == "CAP_GSTREAMER", f"{path}: GST apiPreference"
            assert src.get("gstreamer_available") is True, f"{path}: gstreamer_available"


def test_samples_have_modern_sections() -> None:
    files = _pipeline_json_files(SAMPLES)
    assert len(files) >= 15
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        _assert_common(path, data, require_preview_encoder=True)
        assert "show_main_gui" in (data.get("controller") or {}), f"{path}: show_main_gui"
        assert "gui_enabled" in (data.get("controller") or {}), f"{path}: gui_enabled"


def test_canonical_and_poly_cameras_have_modern_sections() -> None:
    files = []
    for path in _pipeline_json_files(CONFIGS):
        name = path.name
        if name.startswith("poly-videos"):
            continue
        files.append(path)
    assert files
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        _assert_common(path, data, require_preview_encoder=True)


def test_poly_videos_benches_have_server_record_and_gst_flags() -> None:
    files = [p for p in _pipeline_json_files(CONFIGS) if p.name.startswith("poly-videos")]
    assert len(files) >= 20
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        _assert_common(path, data, require_preview_encoder=False)


def test_no_deploy_absolute_media_paths_in_tracked_configs() -> None:
    roots = [SAMPLES, CONFIGS]
    hits: list[str] = []
    for root in roots:
        for path in root.glob("*.json"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "/media/user/" in text:
                hits.append(str(path.relative_to(REPO)))
    assert hits == [], f"absolute Deploy paths remain: {hits}"
