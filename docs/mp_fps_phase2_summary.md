# MP FPS phase 2 summary

Фаза 2: снижение MP backlog без слияния YOLO-процессов. Primary KPI: `mean_staleness_frames`, `mp_pending_max`, `lag_ratio`; `pipeline_hz_est` — вторичный.

## Матрица backlog (3×120 s, opencv process)

Полная таблица: `reports/poly_videos_mode_compare/experiments/backlog_matrix/matrix_results.md`

| exp | pending_max | lag_ratio | mean_staleness | e2e_ratio | score | Примечание |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| **B3** (winner) | 30 | 2.21 | 5.52 | 3.49 | 77.8 | `PIPELINE_SYNC_MP=1` |
| B1 | 31 | 2.29 | 6.23 | 3.20 | 82.0 | drain 0.01 |
| B2 | 33 | 2.14 | 6.23 | 3.20 | 85.2 | + backpressure |
| B4 | 46 | 2.15 | 6.16 | 3.15 | 111.0 | cap + backpressure |
| B5 | 38 | 1.86 | 6.73 | 3.58 | 96.4 | SCALE=2 контроль |

Все варианты: `drop_events=0`. Порог `mean_staleness ≤ 2` не достигнут; лучший score — **B3**.

## Финальный bench (5×180, env B3)

```text
EVILEYE_MP_QUEUE_SCALE=1
EVILEYE_MP_DRAIN_POLL_SEC=0.01
EVILEYE_PIPELINE_SYNC_MP=1
EVILEYE_PIPELINE_SYNC_MP_MS=8
```

| Metric | Baseline | Current (B3) | Δ% | Target | PASS |
| --- | ---: | ---: | ---: | ---: | --- |
| pipeline_hz_est (opencv/process) | 15.34 | 10.87 | -29.1% | ≥ 12 | нет |
| pipeline_hz_est (opencv/thread) | 38.46 | 35.01 | -9.0% | — | — |
| p95_pipeline_ms (opencv/process) | 128 | 159 | +24.6% | — | — |
| mp_pending_max (process) | ~75 (SCALE=2) | 29.4 | — | ≤ 25 | почти |
| lag_ratio mean (process) | 2.67 | 2.18 | — | < 1.5 | нет |
| mean_staleness_frames (process) | — | 6.17 | — | ≤ 2 | нет |
| E2E process/thread ratio | — | 3.24 | — | ≥ 0.70 | да |
| drop_events | 0 | 0 | — | 0 | да |

**Вывод:** `mp_pending` снижен с ~75 до ~29 без `QUEUE_SCALE=2`. E2E process/thread ≫ 0.7. `lag_ratio` и staleness улучшились vs post-fix SCALE=2, но жёсткие K2/K3 не закрыты — метрика staleness чувствительна к unmatched E2E; для production рассмотреть **B2** (backpressure без sync в тике) или доработку sticky/MC.

## Рекомендации

- **Default:** `SCALE=1`, `DRAIN=0.01`; не поднимать `QUEUE_SCALE` без улучшения staleness.
- **Bench / отладка:** B3 (`PIPELINE_SYNC_MP=1`) — лучший score в матрице.
- **Production (осторожно):** B2 `CONTROLLER_BACKPRESSURE=1` или B4 `MP_PENDING_CAP=4` + backpressure.
- Опционально: `EVILEYE_SKIP_PIPELINE_TICK_ON_BACKLOG=1` только для headless bench.

## Код и скрипты

- Pending cap, MpBarrier `put_dropped`/`pending_evict`, controller backpressure
- `run_backlog_matrix.sh`, `compare_poly_backlog_matrix.py`, `run_winner_bench.sh`

Коммиты фазы 2: `96d067c`, `6ec8aca`, `c51112c`, `f63dc30` (+ docs).
