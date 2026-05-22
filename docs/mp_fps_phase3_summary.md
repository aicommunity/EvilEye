# MP FPS phase 3 summary

Фаза 3: максимизация **e2e_tracker_fps** (opencv process) при **mean_staleness ∈ [5.9, 6.5]**. Не оптимизировать снижение staleness.

## Матрица E2E FPS (F0–F7, 3×120 s)

`reports/poly_videos_mode_compare/experiments/e2e_fps_matrix/matrix_results.md`

| exp | e2e_fps | e2e_ratio | staleness | in_band | score |
| --- | ---: | ---: | ---: | --- | ---: |
| **F2 (WINNER)** | **30.05** | **3.23** | **6.32** | да | **31.66** |
| F3 | 29.90 | 3.16 | 6.41 | да | 31.48 |
| F1 | 29.85 | 3.24 | 6.35 | да | 31.47 |
| F0 / F5 | ~31.6–31.8 | ~3.3–3.5 | **<5.9** | нет | disqualified (too fresh) |
| F4 / F6 | ~30.0 | ~3.2 | **>6.5** | нет | disqualified (slightly stale) |

**Вывод:** постоянный `PIPELINE_SYNC_MP=1` (F0/F5) повышает e2e, но выводит staleness ниже 5.9. **F2** — лучший in-band score.

## Production env (WINNER F2)

Значения по умолчанию в коде (`mp_queue_config`, `controller`); явный export не обязателен:

```text
EVILEYE_MP_QUEUE_SCALE=1
EVILEYE_MP_DRAIN_POLL_SEC=0.01
EVILEYE_CONTROLLER_BACKPRESSURE=soft
```

Отключить backpressure: `EVILEYE_CONTROLLER_BACKPRESSURE=0`.

## Финальный bench (5×180, F2 env)

Артефакты: `reports/poly_videos_mode_compare/phase3_final/`

| Metric | Baseline | Current (F2) | Δ% |
| --- | ---: | ---: | ---: |
| pipeline_hz_est (opencv/process) | 15.34 | 9.86 | -35.7% |
| pipeline_hz_est (opencv/thread) | 38.46 | 32.48 | -15.6% |
| p95_pipeline_ms (opencv/process) | 128 | 185 | +44.7% |

## E2E KPI (phase 3 — primary)

| ID | Metric | Current | Target |
| --- | --- | ---: | ---: |
| K1 | e2e_tracker_fps (process) | 29.8724 | ≥ 31 |
| K2 | e2e_ratio process/thread | 3.2246030289618846 | ≥ 3.0 |
| K3 | mean_staleness_frames | 6.506 | [5.9, 6.5] |
| K4 | staleness_in_band | False | true |
| K5 | mp_pending_max | 31.0 | ≤ 45 |
| K6 | drop_events (barrier) | 0 | 0 |

**E2E env:** winner_F2

**Интерпретация:** e2e_ratio vs thread ~3.2× (цель ≥3.0). В матрице F2 staleness 6.32 (in-band); на 5×180 — 6.506 (на 0.006 выше 6.5). Не использовать F0/F5 (staleness too fresh). `pipeline_hz` — диагностика, не primary KPI.

## Код

- `EVILEYE_PIPELINE_SYNC_MP=adaptive`, `EVILEYE_CONTROLLER_BACKPRESSURE=soft`, `EVILEYE_MP_DRAIN_MAX_ITEMS`
- Скрипты: `run_e2e_fps_matrix.sh`, `compare_poly_e2e_fps_matrix.py`, `run_phase3_winner_bench.sh`

Коммиты: `a53629c`, `413f62e`, `4165742`.
