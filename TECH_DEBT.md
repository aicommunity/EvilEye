# Technical debt ledger

Last reviewed: full project audit 2026-11 (see audit/AUDIT_2026-11.md).
Audit fix plan executed 2026-11: stages 0-5 merged into `develop` via
`docs/audit-2026-11`, `fix/audit-s0`, `perf/audit-s1`, `fix/audit-s2`,
`sec/audit-s3`, `ci/audit-s4`, `refactor/audit-s5` (all --no-ff). 29 audit
findings closed (TD-AUD-S0-*..TD-AUD-S5-*); remaining open items below.

## Open

| ID | Description | File / area | Introduced | Target phase | Priority |
|----|-------------|-------------|------------|--------------|----------|
| TD-MP-401 | Capture triple-buffer reduction spike | capture | R4 | Deferred | P2 |
| TD-MP-501 | module_capabilities JSON S4 | configs | — | Deferred | P3 |
| TD-DOC-001 | `DualModeProcessor` adoption by all modules (S1) | core/dual_mode_processor.py | doc audit | Backlog | P3 |
| TD-DOC-001b | RoiFeeder adopts DualModeProcessor (reference) | attributes_detection/roi_feeder.py | audit 2026-09-26 | Done | P3 |
| TD-DOC-002 | `validate_config` JSON `stage_kind` (S6) | scripts/validate_config.py | doc audit | Backlog | P3 |
| TD-PS-D1 | Detector in a multi-detector fanout without `model_class_mapping` is not remapped and does not fail start (B5 follow-up) | pipeline / controller | plugin_support audit | Backlog | P2 |
| TD-PS-D2 | ~~Shared-memory descriptor is re-allocated per `process` stage~~ Segment pool implemented (stage 1); remaining: change-marker on `Frame.image` to skip re-copy for multi-stage fanout of one frame | core/plugin_runtime | plugin_support audit | Stage 1 (audit fix plan) | P2 |
| TD-PS-D3 | Legacy MP detector path is still wired in (`DetectionThreadYoloMp`, `object_detection_yolo_mp.py`, `detection_thread_factory.py`, `mp_queue_config.py`, `validate_config.py`, MP tests). `LegacyProcessorModuleAdapter` has no built-in consumer (only `legacy_processor_protocol` in `base_class.py` for third-party plugins and tests): remove it after a deprecation notice in PLUGINS.md | object_detector, core/plugin_runtime/legacy.py | plugin_support audit | After deprecation window | P2 |
| TD-PS-D4 | Ruff: 805 `F401` left (all non-stdlib: many may register modules or Qt widgets, so they need a manual review per file), 0 `B904`; 43 known `F821` in `scripts/ruff_baseline.json` (optional Qt imports, dialogs). Stdlib `F401` and all `B904` were fixed | repo-wide | plugin_support audit | Gradual | P3 |
| TD-PS-D5 | Merged remote branches (`autorefactor_*`, `*-hotfix`, `experiments`; 45+ on origin) are not cleaned up | git remote | plugin_support audit | Needs owner decision | P3 |
| TD-PS-D6 | Open acceptance criteria: target FPS/p95/loss budget (the old-vs-new comparison, browser alarm smoke and RTSP disconnect check were run on 2026-10-19, see docs/RUNTIME_VERIFICATION_2026-10-19.md) | docs/PLUGIN_MIGRATION_COMPLETION_PLAN.md | plugin_support audit | Before release | P1 |
| TD-PS-D7 | Frame loss vs `main` (82.9% vs 92.5%): all four root causes fixed in stage 1 (crops-only IPC, MpPendingReporter + backlog stats, SHM segment pool, continuous output drainer + queue_size 16 default); A/B re-measurement on the 2688x1520 clip still pending (acceptance criterion: tracker >= 92%, ties into TD-PS-D6) | core/plugin_runtime, core/processor_step | live comparison 2026-10-19 | Verification pending | P1 |
| TD-PS-D8 | ~~Schedule-alarm events carry no frames~~ Fixed in stage 2 (TD-AUD-S2-5) | events_detectors | live alarm check 2026-10-19 | Done | P3 |



| TD-AUD-011 | GUI journals fetch data with synchronous psycopg2 in a QTimer slot (UI freezes); regression vs legacy QThread loader | visualization_modules/unified_events_journal.py | audit 2026-11 | Stage 5 (audit fix plan) | P2 |

## In progress

| ID | Owner / branch | Notes |
|----|----------------|-------|

## Closed

| ID | Closed in phase | Notes |
|----|-----------------|-------|
| TD-AUD-S0-1 | audit fix stage 0 (fix/audit-s0) | Bootstrap admin password no longer logged; stored once in a 0600 note next to credentials.json, removed after first password change; `must_change_password` enforced by AuthGuardMiddleware at the API level |
| TD-AUD-S0-2 | audit fix stage 0 (fix/audit-s0) | CSRF origin check covers all non-GET `/api/v1/*` (was admin-only); internal token compared with `hmac.compare_digest` in ProtectionMiddleware; `/ready` reduced to `{"status":"ok"}`, details moved to protected `/api/v1/system/readiness` (runtime:view) |
| TD-AUD-S0-3 | audit fix stage 0 (fix/audit-s0) | Double `_record_input_drop()` removed (frame-drop counters were inflated ~2x during TD-PS-D7 measurements) |
| TD-AUD-S0-4 | audit fix stage 0 (fix/audit-s0) | MpWorker exits with `MP_EXIT_CRASH=3` on non-CUDA init/loop failures instead of clean 0, so the health monitor sees crashes |
| TD-AUD-S0-5 | audit fix stage 0 (fix/audit-s0) | `CameraEvent.__eq__` compares `other.timestamp`; single `pickle.loads` for worker event output |
| TD-AUD-S0-6 | audit fix stage 0 (fix/audit-s0) | MainWindow None-guards for `controller` in resizeEvent/check_controller_status; dead `api/routes/events.py` removed; stale `visualization.spec` and Py3.9 `__pycache__` legacy dirs removed |
| TD-AUD-S0-7 | audit fix stage 0 (fix/audit-s0) | gitleaks secret-scanning job added to CI (full history) |
| TD-AUD-S1-1 | audit fix stage 1 (perf/audit-s1) | Crops-only IPC for AttributeClassifier restored (pack_process_item/restore_process_result hooks in the plugin runtime; ROI crops cross the process boundary, not the full frame) |
| TD-AUD-S1-2 | audit fix stage 1 (perf/audit-s1) | ItemModuleAdapter/ParallelItemModuleAdapter implement MpPendingReporter; estimate_mp_backlog_stats covers plugin adapters and attributes stages (soft backpressure no longer blind) |
| TD-AUD-S1-3 | audit fix stage 1 (perf/audit-s1) | SHM segment pool in SharedFrameTransport (opt-in; plugin runtime enables it, EVILEYE_SHM_POOL=0 to disable, EVILEYE_SHM_POOL_MAX_FREE): no per-frame create/unlink |
| TD-AUD-S1-4 | audit fix stage 1 (perf/audit-s1) | Continuous output-drainer thread for process-mode plugin modules: worker results decoded as they arrive instead of once per tick; bounded drop-oldest hand-off |
| TD-AUD-S1-5 | audit fix stage 1 (perf/audit-s1) | Default module queue_size 8→16 (EVILEYE_MODULE_QUEUE_SIZE); MpControl queue-swap race fixed with _queues_lock + snapshots (TD-AUD-001) |
| TD-AUD-S1-6 | audit fix stage 1 (perf/audit-s1) | GStreamer: single frame_id increment; get_frames_impl no longer returns the same physical frame twice (freshness key includes connection_generation) (TD-AUD-003) |
| TD-AUD-S1-7 | audit fix stage 1 (perf/audit-s1) | Processor stop loops aggregate errors and keep stopping remaining processors instead of aborting on the first failure (TD-AUD-002) |
| TD-AUD-S2-1 | audit fix stage 2 (fix/audit-s2) | ConfigHistoryManager: execute_query -> query (9 call sites); job statistics rewritten against the real jobs columns (status/frames_processed never existed) (TD-AUD-004) |
| TD-AUD-S2-2 | audit fix stage 2 (fix/audit-s2) | pg_spool: adapter writes that exhaust the retry budget (and events accepted while PG is disconnected) are spooled under <image_dir>/pg_spool and replayed on recovery (200 MB budget, oldest dropped first) (TD-AUD-005) |
| TD-AUD-S2-3 | audit fix stage 2 (fix/audit-s2) | get_next_event_id queries tables individually (one broken table no longer resets ids to 0); get_last_id falls back to an epoch floor instead of 0 (no PK collisions); events_tables filters adapters by storage_backend (TD-AUD-006) |
| TD-AUD-S2-4 | audit fix stage 2 (fix/audit-s2) | Objects writer thread: retries OperationalError via execute_with_retry and logs losses at error level (was: silent drop at info) |
| TD-AUD-S2-5 | audit fix stage 2 (fix/audit-s2) | TD-PS-D8 closed: ScheduleAlarmEvent carries detected/lost frame snapshots; PG and JSON adapters persist previews/frames |
| TD-AUD-S2-6 | audit fix stage 2 (fix/audit-s2) | DB retention: purge_old_records + daily DatabaseService loop behind database.retention_days (default off); EvilEyeData file retention already existed via storage_monitor |
| TD-AUD-S3-1 | audit fix stage 3 (sec/audit-s3) | journal_data_source_db fully parameterized: dates, source names, source/object ids and LIMIT/OFFSET travel as %s params (was f-string SQL with manual escaping) (TD-AUD-007 / W1) |
| TD-AUD-S3-2 | audit fix stage 3 (sec/audit-s3) | /setup/test-database refuses link-local/reserved hosts (cloud-metadata SSRF pivots; loopback/LAN allowed, EVILEYE_SETUP_DB_EXTRA_HOSTS extends); /check-data-dir confined to the site root unless EVILEYE_SETUP_TRUST_DATA_DIR=1 (W3) |
| TD-AUD-S3-3 | audit fix stage 3 (sec/audit-s3) | /auth/me re-resolves the session against the live user store - deleted/disabled users get 401 (W6) |
| TD-AUD-S3-4 | audit fix stage 3 (sec/audit-s3) | uvicorn forwarded_allow_ips synced with web_auth.protection.trusted_proxy_ips; CORS uses explicit methods/headers instead of "*" with credentials (W9) |
| TD-AUD-S3-5 | audit fix stage 3 (sec/audit-s3) | 500 responses no longer leak exception text (configs/extensions); failures logged server-side via logger.exception (W8) |
| TD-AUD-S4-1 | audit fix stage 4 (ci/audit-s4) | CI: mypy ratchet job (scripts/check_mypy_ratchet.py + mypy_baseline.json, 6 seeded modules), integration job with postgres service (continue-on-error until consistently green), pytest-xdist + coverage --cov-fail-under=25 in the 3.12 unit job, develop branch added to push triggers (TD-AUD-008) |
| TD-AUD-S4-2 | audit fix stage 4 (ci/audit-s4) | pre-commit pytest hook reduced to the fast unit subset (tests/unit -x -q); `make test` = unit (matches CI), new test-integration target; lint targets use the ratchet scripts (TD-AUD-013) |
| TD-AUD-S4-3 | audit fix stage 4 (ci/audit-s4) | Docker: HEALTHCHECK hits /ready over HTTP instead of import-checking; postgres published on 127.0.0.1 only and POSTGRES_PASSWORD is required (:? syntax, no default) (TD-AUD-014; non-root USER deliberately deferred - host-mounted data dirs assume root today) |
| TD-AUD-S4-4 | audit fix stage 4 (ci/audit-s4) | SQLAlchemy removed from pyproject/requirements (declared, never imported); scripts/setup/fix_entry_points.py removed along with its Makefile/install.py/README call sites - pip console-scripts are the single mechanism (TD-AUD-015) |
| TD-AUD-S4-5 | audit fix stage 4 (ci/audit-s4) | site_runtime_guard works on Windows (psutil environ/cwd with /proc fallback); watchdog matches the config stem as a whole word (?<!\w)/(?!\w) - short config names no longer match unrelated cmdlines |
| TD-AUD-S5-1 | audit fix stage 5 (refactor/audit-s5) | Dead GUI journal generation removed: events_journal.py, handler_journal_view.py, objects_journal_json.py, both data loaders, table_data_thread.py, table_updater_view.py (~2700 lines) + their 22 integration tests (TD-AUD-009) |
| TD-AUD-S5-2 | audit fix stage 5 (refactor/audit-s5) | VideoThread label index comes from the stable source_index_map instead of the never-resetting class counter - frames no longer silently dropped after visualizer re-init (TD-AUD-010) |
| TD-AUD-S5-3 | audit fix stage 5 (refactor/audit-s5) | Hardcoded 80-entry COCO dict moved from Controller.__init__ to ClassManager.DEFAULT_COCO_CLASS_MAPPING (TD-AUD-012, partial: full ControllerBootstrap decomposition still open) |
| TD-AUD-S5-4 | audit fix stage 5 (refactor/audit-s5) | PipelineSurveillance: five ProcessorStep _init_* copy-pastes replaced by _init_step_processors (detectors/trackers/mc_trackers/attributes_roi/classifier) |
| TD-AUD-S5-5 | audit fix stage 5 (refactor/audit-s5) | sys.path.append repo-root hacks removed from 9 visualization modules (+pruned unused sys/Path imports) |
| TD-AUD-S5-6 | audit fix stage 5 (refactor/audit-s5) | Legacy MP detector deprecation notice added to docs/PLUGINS.md (TD-PS-D3 window opened) |
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
| TD-010 | TD-010 | GStreamer split into mixins; `ControllerProcessingMixin`; init/recording services |
| TD-011 | completion | `EventImageWriter` for PG db adapters |
| TD-012 | completion | `botsort_config.py` shared by thread + `MpWorkerTracker` |
| TD-013 | completion | `test_yolo_mp_subprocess.py` child-process guard |
| TD-014 | completion | `materialize_payload_item` in `MpWorkerTracker._unpack_input` |
| TD-015 | completion | `stream_player` `conftest.py` + README |
| TD-016 | completion | unit pytest + integration subset + KPI gate PASS `20260521_145543` |
| TD-017 | completion | MULTIPROCESSING/CONFIGURATION_GUIDE YOLO thread + memory notes |
| TD-MP-001 | R0 | Legacy ObjectDetectorYoloMp documented in MULTIPROCESSING |
| TD-MP-101 | R1 | Tracker/detector wired to MpAsyncBridge |
| TD-MP-201 | R3 | MpPendingReporter replaces isinstance backlog probe |
| TD-MP-110 | R2 | frame_to_worker_meta replaces getattr in _pack_for_worker |
| TD-MP-301 | MEM-4 | soak_mp_memory.sh added (manual gate) |
| TD-MP-102 | R2/DUP-016 | AttributeClassifier uses YoloRuntime (thread + mp worker) |
| TD-MP-601 | S6 | validate_config warns legacy YoloMp + mc_trackers process |
| TD-MP-401-doc | R4 | capture_buffer_levels.md spike — keep 3 levels |
| TD-DOC-003 | doc audit 2026-05-22 | Full docs sync R0–R6 + DOC_AUDIT_MATRIX |
| A1 | plugin_support stage 1 | `process_item` errors no longer stop a module: `error_policy` (`skip_item` default, `restart`, `fail_stop`), burst escalation, restart budget |
| A2 | plugin_support stage 1 | `mp_restart_on_exit` / `mp_no_restart_exit_codes` mapped to the policy, validated, kept out of module config; SIGKILL restarts the pool on fresh queues |
| A3, C3 | plugin_support stage 1 | Missing imports (`os`, `queue.Empty`, `CaptureConfigurationError`, `typing.Any`) fixed with regression tests |
| B1 | plugin_support stage 2 | Broken entry point is isolated (`failed_plugins`), `EVILEYE_DISABLED_PLUGINS` and UI disable |
| B2 | plugin_support stage 2 | Builder rejects proxy headers without `trust_proxy`; `builder_allowed_ips`; docs in WEB_UI_REVERSE_PROXY.md |
| B3 | plugin_support stage 2 | Plugin names may not shadow stdlib/importable modules |
| B4 | plugin_support stage 2 | Builder endpoints run in the threadpool; protection config and catalog cached |
| CSRF | plugin_support stage 2 | Foreign Origin/Referer rejected for non-GET `/api/v1/admin/*`; password re-entry for plugin install |
| C4 | plugin_support stage 2 | Inter-process status lock, `completed` only after the plugin loaded, history rotation (100), dead systemd branch removed |
| B5 | plugin_support stage 3 | Detector class ids are remapped to the global `ClassManager` space before the fanout join (see TD-PS-D1) |
| B6 | plugin_support stage 3 | `degraded` uses a sliding window (`EVILEYE_DEGRADED_WINDOW_SEC`); Prometheus export at `/api/v1/system/metrics` |
| C1, C2 | plugin_support stage 3 | Fanout defaults 3 s / 64 frames; `None` from a detector is a valid empty answer |
| C5 | plugin_support stage 3 | Process-boundary `Frame` fields documented; segment reuse deferred (TD-PS-D2) |
| CI | plugin_support stage 0 | `.github/workflows/ci.yml`; new F821/E9 findings block merging |

## Task notes

2026-10-31 recheck: TD-PS-D7 remains open. Three identical runs: main median tracker output 92.5%, final event-restore candidate 83.0% (all runs exit 0). See the dated addendum in `docs/RUNTIME_VERIFICATION_2026-10-19.md`.

### TD-PS-D7: frame loss on `plugin_support` compared with `main`

**Symptom.** On identical load the branch delivers fewer frames to the tracker output. Load: one camera,
60 s clip (901 frames, 2688x1520, 15 fps, H.264, played in real time), `ObjectDetectorYolo` (`yolo11m.pt`)
plus BoT-SORT, rest of the pipeline from `configs/hardhat_1cam.json`, headless, RTX 3060.
Metric: share of frames that reach the tracker output, from the `EVILEYE_PERF_DIAG` counters that exist in both
trees (median of 3 runs).

| Variant | Into detector | Out of tracker | Loss |
| --- | --- | --- | --- |
| `main` (`b18f81e`) | 99.9-100% | 92.3-92.6% | 7.4-7.7% |
| branch, defaults | 100% | 82.7-83.0% | 17.0-17.3% |
| branch, `queue_size=32` on detector and tracker | 100% | 85.0-85.7% | 14.3-15.0% |
| branch, detector and tracker in `thread` mode | 99.9-100% | 76.8-76.9% | 23.1-23.2% |

Branch queue counters at the end of a run: detector dropped 60-62 frames, tracker 90-91, attribute classifier
11-13. The wall time is equal for both trees (the source is paced at real time), so throughput is not visible
there; loss is. Full method and numbers: `docs/RUNTIME_VERIFICATION_2026-10-19.md`.

**What is already ruled out.** Queue size explains only about 2-3 pp. The `process` mode is not the cause
(`thread` is worse because of the GIL). Detector input is complete (100%), so frames are lost inside and after
the detector, not at the source.

**Hypotheses to check, in order of cost.**

1. Stage timeline: run with `EVILEYE_PIPELINE_TIMELINE=1` and `EVILEYE_PERF_DIAG=1`, find which stage is the
   bottleneck (detector 60 drops, tracker 90 drops).
2. Pickling of the input item in `ItemModuleAdapter.put` for modules that do not declare `accepts_frame_handle`:
   a 2688x1520 BGR frame is about 12 MB per put.
3. Per-stage copy into a new shared-memory segment (`_prepare_item_for_process`, see TD-PS-D2): about 12 MB per
   frame per `process` stage, several stages per frame.
4. Extra work in the branch pipeline: `RoiFeeder` and `AttributeClassifier` run in separate workers and compete
   for the GPU and the CPU; compare with a config without the `attributes_*` sections on both trees.
5. Drop-oldest on a full queue of 8 versus the larger/blocking buffers of the legacy path in `main`.

**How to reproduce.** On the server (global python, no `.venv`):

```bash
git worktree add --detach /tmp/eye_main b18f81e48974317f33ac9f2c3c45542a67ce8f7b && ln -s ~/EvilEye/models /tmp/eye_main/models
python scripts/runtime_compare.py --video ~/EvilEye/videos/2-GTK_UMPN_ICHI_20250912_082734_trim.mp4 \
    --seconds 60 --runs 3 --tree main=/tmp/eye_main --tree branch=$HOME/EvilEye
```

Options: `--queue-size N` and `--execution-mode thread|process` override the branch's detector/tracker settings,
`--no-tracker` drops the tracker. Remove the worktree afterwards (`git worktree remove --force /tmp/eye_main`).

**Done when.**

- the stage that loses the frames is identified and the cause is documented;
- on the same clip and config the share of frames at the tracker output on the branch is not lower than on
  `main` (about 92%), or the remaining difference is explained and accepted;
- a counter or a test catches the regression (for example per-stage "frames in / frames out" in the runtime
  telemetry, and a unit test for the changed code path);
- `docs/RUNTIME_VERIFICATION_2026-10-19.md` and the table above are updated with the new numbers.

**Related.** TD-PS-D2 (shared-memory segment per stage), TD-PS-D6 (target FPS, p95 and loss budget must be fixed
before this can be called finished).

## Deferred (explicitly out of scope)

| ID | Reason |
|----|--------|
| TD-DB-BATCH | Full DB batching in adapters — feature work per REFACTORING_PROGRESS |
| TD-GUI-SPLIT | Full `main_window.py` decomposition — needs dedicated GUI regression suite |
| TD-YOLO-SINGLETON | Shared YOLO model cache — forbidden (thread/process safety) |
| TD-018 | `capture/` materialize_frame in gstreamer path — low ROI; SHM owned by capture callbacks |

## Remaining known items (post stage-2)

- JSON event journal rewrites the whole daily file per event (O(n^2) on heavy days) - switch to NDJSON append with readers support (deferred; needs a coordinated reader update).

## Known environment-dependent test failures (Windows dev host, pre-existing)

Verified failing on the clean baseline before the audit fixes; not regressions:
- `tests/unit/core/test_process_control.py` (3) - POSIX process groups unavailable
- `tests/unit/capture/test_gstreamer_release_lifecycle.py`, `test_recording_queue_start_not_leaky.py` - GStreamer env assumptions
- `tests/unit/controller/test_runtime_diagnostics.py::test_runtime_stats_control_command_round_trips_over_control_ipc` - IPC on Windows
- `tests/integration/visualization/configurer/test_configurer_simple.py` - cross-drive relpath (C:/E:)

## Post-stage-5 notes

- Some test still calls `create_app()`/bootstrap without chdir and can add a
  `web_auth` section to a real `<cwd>/credentials.json` during full-suite runs;
  the diagnostics guard test is now isolated via `EVILEYE_SITE_DIR`. Hunting the
  polluter is a follow-up (small, P3).
- TD-PS-D7: root causes fixed in stage 1; the A/B re-measurement on the
  2688x1520 clip (acceptance: tracker >= 92%, tied to TD-PS-D6) still has to run
  on the GPU host.
- Docker non-root `USER` deliberately deferred: existing host-mounted data dirs
  assume root ownership (documented in TD-AUD-S4-3).
