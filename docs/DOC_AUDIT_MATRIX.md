# Documentation audit matrix

Last full pass: **2026-05-22** (branch `mt_refactoring2`, post MP refactor R0–R6).

**Legend:** `OK` | `Stale` | `Partial` | `Missing` | `N/A`

| Document | Code owner | Role | Status | Notes |
|----------|------------|------|--------|-------|
| docs/thread_vs_mp_contracts.md | core/, det/, track/ | Contract | **OK** | §15 index, MpAsyncBridge |
| docs/thread_vs_mp_refactoring_plan.md | same | Changelog | **OK** | Implemented + gate |
| docs/module_integration_simplification.md | core/ | S* roadmap | **OK** | S1/S6 Partial noted |
| docs/developing_dual_mode_modules.md | core/ | Dev guide | **OK** | bridge checklist |
| docs/MULTIPROCESSING.md | core/, capture/ | Ops | **OK** | § MP tuning env, bridge, capture_buffer |
| docs/capture_buffer_levels.md | capture/ | MP buffers | **OK** | |
| docs/mp_fps_phase2_summary.md | bench | Historical | **OK** | |
| docs/mp_fps_phase3_summary.md | bench | Historical + gate | **OK** | Post-refactor § |
| docs/mp_fps_post_fix_summary.md | bench | Historical | **OK** | |
| docs/multiprocessing_benchmark.md | scripts/ | Bench | **OK** | bridge cap wording; nav → diploma runbook |
| docs/diploma_benchmark_methodology.md | scripts/ | Bench runbook | **OK** | Full repro: matrix, gate, KPI, metrics |
| docs/BENCHMARKS_MERGE_SCOPE.md | — | Merge guide | **OK** | Scope benchmarks → main |
| docs/ARCHITECTURE.md | all | Architecture | **OK** | MP boundary § L5 |
| docs/PIPELINE_ARCHITECTURE.md | pipelines/ | Pipeline | **OK** | ProcessorStep MP |
| docs/CONFIGURATION_GUIDE.md | core/ | Config | **OK** | execution_mode, register table |
| docs/MT_REFACTORING2_CHANGES.md | — | Changelog | **OK** | R0–R6 section |
| docs/README.md | — | Index | **OK** | MP reading order |
| README.md (root) | — | Entry | **OK** | thread/MP links |
| docs/CODE_MODULE_INDEX.md | evileye/ | Index | **OK** | |
| docs/ATTRIBUTES_DETECTION_README.md | attributes/ | Feature | **OK** | YoloRuntime ref via contracts |
| docs/VideoCaptureGStreamer_Usage.md | capture/ | Feature | **OK** | § execution_mode + queue_policy |
| docs/VIDEO_CAPTURE_OPENCV_ISSUES.md | capture/ | Issues | **OK** | |
| docs/GUI_REFACTORING_GUIDE.md | visualization/ | Feature | **OK** | |
| docs/DEPENDENCY_INJECTION_GUIDE.md | core/di | Feature | **OK** | |
| docs/CLI_DEPLOY_COMMAND.md | cli | Feature | **OK** | |
| docs/DATABASE_SETUP_GUIDE.md | database/ | Feature | **OK** | |
| docs/STREAMING_REFACTOR_NOTES.md | controller/ | Feature | **OK** | |
| docs/LABELING_SYSTEM_README.md | objects_handler/ | Feature | **N/A** | No MP terms |
| docs/CREATE_SCRIPT_README.md | — | Tooling | **N/A** | |
| docs/TEXT_RENDERING_SYSTEM.md | visualization/ | Feature | **N/A** | |
| docs/CONFIG_HISTORY_USER_GUIDE.md | — | Feature | **N/A** | |
| docs/ImageSequence_GStreamer_Usage.md | capture/ | Feature | **N/A** | |
| tests/README.md | tests/ | Tests | **OK** | MP unit table |
| tests/TESTS_INDEX.md | tests/ | Tests | **OK** | MP section |
| TECH_DEBT.md | — | Debt | **OK** | TD-DOC-* |
| REFACTORING_PROGRESS.md | — | Progress | **OK** | Doc audit 2026-05-22 entry |
| configs/README_SAMPLES.md | configs/ | Samples | **OK** | |
| reports/mp_refactor_gate/e2e_gate_summary.md | gate | Raw | **OK** | Source for docs |

## Register types (`@EvilEyeBase.register`)

| type | Module | CONFIGURATION_GUIDE |
|------|--------|-------------------|
| ObjectDetectorYolo | object_detection_yolo.py | Yes |
| ObjectDetectorYoloMp | object_detection_yolo_mp.py | Deprecated |
| ObjectDetectorRtdetr / Rfdetr | object_detection_*.py | Yes |
| ObjectTrackingBotsort | object_tracking_botsort.py | Yes |
| ObjectMultiCameraTracking | custom_object_tracking.py | Yes (sync only) |
| VideoCaptureGStreamer / Opencv | capture/ | Yes |
| AttributeClassifier / Detector / RoiFeeder | attributes_detection/ | ATTRIBUTES doc |
| PreprocessingPipeline | preprocessing/ | Yes |

## EVILEYE_* (MP-relevant)

| Variable | Default | MULTIPROCESSING |
|----------|---------|-----------------|
| EVILEYE_MP_QUEUE_SCALE | 1 | Yes |
| EVILEYE_MP_DRAIN_POLL_SEC | 0.01 | Yes |
| EVILEYE_MP_PENDING_CAP | derived | Yes |
| EVILEYE_CONTROLLER_BACKPRESSURE | soft | Yes |
| EVILEYE_PIPELINE_SYNC_MP | — | contracts §8 |

## DoD (doc audit)

| ID | Status |
|----|--------|
| D1 | Pass — MP/Arch/Config cluster OK |
| D2 | Pass — `_mp_pending` only as `_mp_pending_snapshot` (code name) or historical «было» |
| D3 | Pass — COUP-004 Closed aligned §6.3 / §11b |
| D4 | Pass — docs/README lists MP docs + matrix + gate |
| D5 | Pass — register table in CONFIGURATION_GUIDE |
| D6 | Pass — env в MULTIPROCESSING § pipeline tuning + matrix |
| D7 | Pass — gate in refactoring_plan + phase3 summary |
