"""Regression tests: names that used to be undefined (NameError) at runtime."""
import importlib
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]

CHECKED_FILES = [
    "evileye/capture/gstreamer_capture_pipeline.py",
    "evileye/capture/gstreamer_capture_frames.py",
    "evileye/capture/video_capture_opencv.py",
    "evileye/database_controller/db_adapter_attribute_events.py",
]


def test_attribute_event_get_img_path_uses_os(tmp_path):
    pytest.importorskip("psycopg2")
    module = importlib.import_module("evileye.database_controller.db_adapter_attribute_events")
    adapter = module.DatabaseAdapterAttributeEvents.__new__(module.DatabaseAdapterAttributeEvents)
    adapter.db_params = {"image_dir": str(tmp_path)}
    event = SimpleNamespace(
        object_id=7,
        matched_event_name="helmet",
        timestamp=datetime(2026, 1, 2, 3, 4, 5),
        get_time_finished=lambda: datetime(2026, 1, 2, 3, 4, 9),
    )
    found = adapter._get_img_path("preview", "attribute_found", event, time_stamp=event.timestamp)
    finished = adapter._get_img_path("frame", "attribute_finished", event, time_lost=event.get_time_finished())
    assert "FoundPreviews" in found and found.endswith("_obj7_preview.jpeg")
    assert "LostFrames" in finished and finished.endswith("_obj7_frame.jpeg")
    assert (tmp_path / "Events" / "2026-01-02" / "Images" / "FoundPreviews").is_dir()


def test_capture_configuration_error_importable_in_opencv_capture():
    pytest.importorskip("cv2")
    module = importlib.import_module("evileye.capture.video_capture_opencv")
    assert module.CaptureConfigurationError.__name__ == "CaptureConfigurationError"


def test_gstreamer_mixins_define_empty_and_any():
    pytest.importorskip("numpy")
    for name in ("gstreamer_capture_pipeline", "gstreamer_capture_frames"):
        try:
            module = importlib.import_module(f"evileye.capture.{name}")
        except ImportError as exc:  # GStreamer bindings may be absent
            pytest.skip(f"cannot import {name}: {exc}")
        assert hasattr(module, "Empty")
    frames = importlib.import_module("evileye.capture.gstreamer_capture_frames")
    assert hasattr(frames, "Any")


def test_no_undefined_names_in_fixed_files():
    ruff = shutil.which("ruff")
    cmd = [ruff] if ruff else [sys.executable, "-m", "ruff"]
    try:
        result = subprocess.run(
            cmd + ["check", "--select", "F821", "--no-cache", *CHECKED_FILES],
            cwd=ROOT, capture_output=True, text=True,
        )
    except FileNotFoundError:
        pytest.skip("ruff not installed")
    if "No module named ruff" in result.stderr:
        pytest.skip("ruff not installed")
    assert result.returncode == 0, result.stdout + result.stderr
