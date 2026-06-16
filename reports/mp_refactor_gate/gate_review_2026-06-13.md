# MP refactor gate review (2026-06-13)

Проверка на HEAD ветки `benchmarks` после добавления runbook-документации.

## Unit tests

```bash
python3 -m pytest tests/unit/core/test_mp_*.py \
  tests/unit/object_detector/test_detection_thread_yolo_mp_async.py \
  tests/unit/object_detector/test_yolo_mp_subprocess.py \
  tests/unit/object_tracker/test_botsort_parent_init.py \
  tests/unit/object_tracker/test_tracker_mp_dispatch_contract.py \
  tests/unit/capture/test_queue_policy.py \
  tests/unit/pipeline/test_pipeline_results_selection_mode.py \
  tests/unit/scripts/test_prepare_multiprocessing_benchmark.py \
  tests/unit/scripts/test_render_multiprocessing_benchmark_report.py \
  tests/unit/scripts/test_benchmark_ipc_kpi_gate.py -q
```

**Результат:** PASS (exit 0).

## IPC KPI gate

```bash
python3 scripts/run_ipc_kpi_gate.py --profile configs/kpi_gate_profile.json
```

**Результат:** PASS — `reports/ipc_kpi_gate_20260613_132855/report.md`

## E2E smoke (30 s active, 10 s warmup)

Env F2: `EVILEYE_MP_DRAIN_POLL_SEC=0.01`, `EVILEYE_CONTROLLER_BACKPRESSURE=soft`

| Config | e2e_tracker_fps | staleness_in_band | mean_staleness |
|--------|-----------------|-------------------|----------------|
| poly-videos (process) | 19.38 | **true** | 6.35 |
| poly-videos-thread | 7.65 | false | — |

**e2e_ratio** (process/thread): **2.53** (gate ≥ 3.0) — **FAIL на коротком smoke**

> Исторический gate (2026-05-22, 90 s): ratio **3.10** — см. [e2e_gate_summary.md](e2e_gate_summary.md).  
> Для зачётной проверки используйте **90 s active + 25 s warmup** по [diploma_benchmark_methodology.md](../../docs/diploma_benchmark_methodology.md#5-сценарий-c--mp-refactor-gate).

## Memory soak

**Не перезапускался** в этой проверке (30 min). Последний зачётный прогон: 2026-05-22, RSS ~748 MB flat — см. [e2e_gate_summary.md](e2e_gate_summary.md).

## Вывод

- Код и KPI gate стабильны на текущем HEAD.
- Полный E2E gate (90 s) и soak рекомендуется перезапустить перед merge в `main`.
