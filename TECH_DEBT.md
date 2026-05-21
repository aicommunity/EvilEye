# Technical debt ledger

Last reviewed: phase 1, 2026-05-21

## Open

| ID | Description | File / area | Introduced | Target phase | Priority |
|----|-------------|-------------|------------|--------------|----------|
| TD-007 | Controller hub imports + deprecated init vs services | `controller/controller.py` | audit | 2 | medium |
| TD-008 | Duplicate journal/stream_player integration tests | `tests/integration/` | audit | 5 | low |
| TD-009 | `api/core` vs `evileye/core` naming collision | `evileye/api/core/` | audit | 5 | low |
| TD-010 | `video_capture_gstreamer.py` / `controller.py` very large | capture, controller | audit | 4 | medium |

## In progress

| ID | Owner / branch | Notes |
|----|----------------|-------|

## Closed

| ID | Closed in phase | Notes |
|----|-----------------|-------|
| TD-002 | phase 0 | Removed duplicate `DetectionThreadFactory` in `detection_thread_factory.py` |
| TD-005 | phase 0 | Doc/CLI gaps D1–D6, D8–D10 addressed in README, Makefile, MULTIPROCESSING, launch/process |
| TD-006 | phase 0 | `tool.coverage.run.source` uses `evileye` package prefix |
| TD-D7 | user | `__version__ = "0.0.9"` aligned with pyproject |
| TD-001 | phase 1 | Removed dead `_preload_models` from `object_detection_base.py` |
| TD-003 | phase 1 | AttributeClassifier loads YOLO in `processing_thread` |
| TD-004 | phase 1 | `stop()` releases model in detection threads (yolo, rtdetr, attribute_detection_thread) |

## Deferred (explicitly out of scope)

| ID | Reason |
|----|--------|
| TD-DB-BATCH | Full DB batching in adapters — feature work per REFACTORING_PROGRESS |
| TD-GUI-SPLIT | Full `main_window.py` decomposition — needs dedicated GUI regression suite |
| TD-YOLO-SINGLETON | Shared YOLO model cache — forbidden (thread/process safety) |
