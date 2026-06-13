#!/usr/bin/env python3
"""Extract Controller processing-loop helpers into a mixin module."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "evileye/controller/controller.py"
OUT = ROOT / "evileye/controller/controller_processing_mixin.py"

PROCESSING_METHODS = {
    "_get_frame_timestamp_sec",
    "_process_pipeline_results",
    "_has_non_empty_payload",
    "_extract_track_ids",
    "_update_track_continuity_diag",
    "_process_tracking_results",
    "_process_events_once",
    "_collect_preview_objects_by_source",
    "_get_preview_event_entries",
    "_get_preview_visualizer_cfg",
    "_get_preview_event_cfg",
    "_extract_preview_zones",
    "_build_preview_render_context",
    "_publish_latest_frame_to_broker",
    "_check_memory_and_maybe_stop",
    "_convert_results_for_visualization",
    "_create_object_from_detection",
    "_create_object_from_track",
    "_maybe_update_visualization",
}

HEADER = '''"""Processing-loop helpers extracted from Controller (TD-010)."""

from __future__ import annotations

import datetime
import pprint
import time

from evileye.object_detector.object_detection_base import DetectionResultList
from evileye.object_tracker.tracking_results import TrackingResultList, TrackingResult
from evileye.core.tracking_dto import ensure_tracking_result_list
from evileye.objects_handler.object_result import ObjectResult, ObjectResultList
from evileye.visualization_modules.preview_render import PreviewRenderContext

'''


def main() -> None:
    source = SRC.read_text(encoding="utf-8")
    mod = ast.parse(source)
    lines = source.splitlines(keepends=True)
    class_node = next(n for n in mod.body if isinstance(n, ast.ClassDef) and n.name == "Controller")

    method_chunks: dict[str, str] = {}
    for stmt in class_node.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            method_chunks[stmt.name] = "".join(lines[stmt.lineno - 1 : stmt.end_lineno])

    missing = PROCESSING_METHODS - set(method_chunks)
    if missing:
        raise RuntimeError(f"Missing methods: {sorted(missing)}")

    parts = [HEADER, "class ControllerProcessingMixin:\n"]
    for name in sorted(PROCESSING_METHODS, key=lambda n: n):
        parts.append(method_chunks[name])
        if not method_chunks[name].endswith("\n"):
            parts.append("\n")
    OUT.write_text("".join(parts), encoding="utf-8")
    print(f"Wrote {OUT}")

    new_source_lines = []
    insert_import = "from evileye.controller.controller_processing_mixin import ControllerProcessingMixin\n"
    import_done = False
    for i, line in enumerate(lines):
        if not import_done and line.startswith("class Controller"):
            new_source_lines.append(insert_import)
            new_source_lines.append("\n")
            new_source_lines.append("class Controller(ControllerProcessingMixin):\n")
            import_done = True
            continue
        if line.startswith("class Controller"):
            continue
        skip = False
        if class_node.lineno <= i + 1 <= (class_node.end_lineno or 0):
            for stmt in class_node.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name in PROCESSING_METHODS:
                    if stmt.lineno <= i + 1 <= stmt.end_lineno:
                        skip = True
                        break
        if skip:
            continue
        new_source_lines.append(line)

    SRC.write_text("".join(new_source_lines), encoding="utf-8")
    print(f"Rewrote {SRC}")


if __name__ == "__main__":
    main()
