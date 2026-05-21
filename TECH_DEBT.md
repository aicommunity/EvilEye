# Technical debt ledger

Last reviewed: TD-008/TD-009, 2026-05-21

## Open

| ID | Description | File / area | Introduced | Target phase | Priority |
|----|-------------|-------------|------------|--------------|----------|
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
| TD-007 | phase 2–4 | Events/config delegates; `ProcessingService` loop helpers; partial controller slimming |
| TD-003-phase3 | phase 5 follow-up | All JSON event adapters use `json_event_io` (+ `event_image_paths` where images) |
| TD-005b | phase 5 follow-up | README D9/D10, server options, CLI_DEPLOY credentials |
| TD-006b | phase 5 follow-up | GStreamer `_log_resource_stats` uses `resource_stats` helper |
| TD-008-partial | phase 5 | Removed `test_attributes_detection.py.unittest_backup` |
| TD-008 | TD-008/TD-009 | Events journal: `conftest`/`helpers`, removed log-only dupes, moved legacy `journal/` tests |
| TD-009 | TD-008/TD-009 | `broker_access`/`manager_access` thin shims → `runtime_services`; tests use canonical accessors |

## Deferred (explicitly out of scope)

| ID | Reason |
|----|--------|
| TD-DB-BATCH | Full DB batching in adapters — feature work per REFACTORING_PROGRESS |
| TD-GUI-SPLIT | Full `main_window.py` decomposition — needs dedicated GUI regression suite |
| TD-YOLO-SINGLETON | Shared YOLO model cache — forbidden (thread/process safety) |
