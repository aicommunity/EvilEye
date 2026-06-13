#!/usr/bin/env python3
"""Split video_capture_gstreamer.py into mixin modules."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "evileye/capture/video_capture_gstreamer.py"
CAPTURE = ROOT / "evileye/capture"

RECORDING_METHODS = {"_setup_recording_branch", "_cleanup_recording_branch"}
DIAGNOSTICS_METHODS = {
    "_maybe_schedule_malloc_trim",
    "_start_notify_worker",
    "_stop_notify_worker",
    "_log_resource_stats",
    "_record_perf_metrics",
    "_log_perf_stats",
}
PIPELINE_METHODS = {
    "_teardown_pipeline",
    "_mask_credentials_in_pipeline",
    "_gst_has",
    "_build_pipeline",
    "_build_pipeline_candidates",
    "_init_pipeline",
    "_on_bus_message",
    "_seek_to_start",
    "_start_main_loop",
    "_stop_main_loop",
}
FRAME_METHODS = {
    "_extract_frame_data",
    "_process_gstreamer_frame_metadata",
    "_store_frame",
    "_notify_subscribers_async",
    "_on_new_sample",
    "get_frames_impl",
    "_grab_frames",
    "_reconnect_loop",
    "_retrieve_frames",
}
MAIN_METHODS = {
    "__init__",
    "init",
    "start",
    "release",
    "is_opened",
    "default",
    "init_impl",
    "release_impl",
    "reset_impl",
    "set_params_impl",
    "get_params_impl",
    "calc_memory_consumption",
    "get_source_info",
}

MIXIN_SPECS = [
    ("gstreamer_capture_recording.py", "GStreamerCaptureRecordingMixin", RECORDING_METHODS, True),
    ("gstreamer_capture_diagnostics.py", "GStreamerCaptureDiagnosticsMixin", DIAGNOSTICS_METHODS, False),
    ("gstreamer_capture_pipeline.py", "GStreamerCapturePipelineMixin", PIPELINE_METHODS, False),
    ("gstreamer_capture_frames.py", "GStreamerCaptureFramesMixin", FRAME_METHODS, False),
]

SHARED_HEADER = '''"""GStreamer capture mixin — see video_capture_gstreamer.py."""

from __future__ import annotations

import threading
import time
import datetime
from typing import Optional, List, Tuple, Any
from queue import Queue, Empty, Full
from collections import deque

import cv2
import numpy as np

from .constants import CaptureConstants
from .exceptions import CaptureInitializationError, CaptureConnectionError
from ..core.frame import CaptureImage, Frame

try:
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst, GLib
except ImportError:
    Gst = None
    GLib = None

from evileye.video_recorder.recorder_base import SourceMeta
from evileye.video_recorder.continuous_recorder_gst import GstContinuousRecorder

'''


def main() -> None:
    source = SRC.read_text(encoding="utf-8")
    mod = ast.parse(source)
    lines = source.splitlines(keepends=True)

    class_node = next(
        n for n in mod.body if isinstance(n, ast.ClassDef) and n.name == "VideoCaptureGStreamer"
    )
    preamble = "".join(lines[: class_node.lineno - 1])
    method_chunks: dict[str, str] = {}
    class_attr_lines: list[str] = []

    for stmt in class_node.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            method_chunks[stmt.name] = "".join(lines[stmt.lineno - 1 : stmt.end_lineno])
        elif isinstance(stmt, ast.Assign):
            class_attr_lines.append("".join(lines[stmt.lineno - 1 : stmt.end_lineno]))

    assigned: set[str] = set()
    for filename, cls_name, names, include_error in MIXIN_SPECS:
        parts = [SHARED_HEADER]
        if include_error:
            parts.append(
                "class _RecordingFilesystemError(RuntimeError):\n"
                '    """Raised when recording output directory is not writable/available."""\n\n'
            )
        parts.append(f"class {cls_name}:\n")
        for name in sorted(names, key=lambda n: (n.startswith("_cleanup"), n)):
            parts.append(method_chunks[name])
            if not method_chunks[name].endswith("\n"):
                parts.append("\n")
            assigned.add(name)
        (CAPTURE / filename).write_text("".join(parts), encoding="utf-8")
        print(f"Wrote {filename} ({len(names)} methods)")

    remaining = set(method_chunks) - assigned
    if remaining != MAIN_METHODS:
        raise RuntimeError(f"assign mismatch extra={remaining-MAIN_METHODS} missing={MAIN_METHODS-remaining}")

    preamble = preamble.replace(
        "class _RecordingFilesystemError(RuntimeError):\n"
        '    """Raised when recording output directory is not writable/available."""\n\n\n',
        "",
    )
    mixin_imports = (
        "from .gstreamer_capture_recording import (\n"
        "    GStreamerCaptureRecordingMixin,\n"
        "    _RecordingFilesystemError,\n"
        ")\n"
        "from .gstreamer_capture_diagnostics import GStreamerCaptureDiagnosticsMixin\n"
        "from .gstreamer_capture_pipeline import GStreamerCapturePipelineMixin\n"
        "from .gstreamer_capture_frames import GStreamerCaptureFramesMixin\n\n"
    )
    preamble = preamble.replace("@EvilEyeBase.register(\"VideoCaptureGStreamer\")\n", "")
    preamble = preamble.rstrip() + "\n\n" + mixin_imports

    main_parts = [
        preamble,
        "@EvilEyeBase.register(\"VideoCaptureGStreamer\")\n",
        "class VideoCaptureGStreamer(\n",
        "    GStreamerCaptureRecordingMixin,\n",
        "    GStreamerCaptureDiagnosticsMixin,\n",
        "    GStreamerCapturePipelineMixin,\n",
        "    GStreamerCaptureFramesMixin,\n",
        "    VideoCaptureBase,\n",
        "):\n",
    ]
    for attr in class_attr_lines:
        main_parts.append(attr if attr.endswith("\n") else attr + "\n")
    if class_attr_lines:
        main_parts.append("\n")

    for name in sorted(MAIN_METHODS, key=lambda n: (n != "__init__", n)):
        main_parts.append(method_chunks[name])
        if not method_chunks[name].endswith("\n"):
            main_parts.append("\n")

    SRC.write_text("".join(main_parts), encoding="utf-8")
    print(f"Rewrote {SRC.name}")


if __name__ == "__main__":
    main()
