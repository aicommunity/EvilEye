# MP FPS post-fix summary

Коммиты: `e671955` (скрипты), `c8d6c8c` (очереди/drain/модель), `d82b1bc` (MpBarrier, sync/backpressure).

## Bench post-fix

Параметры: `EVILEYE_MP_QUEUE_SCALE=2`, `EVILEYE_MP_DRAIN_POLL_SEC=0.01`, 5×180 с, 20/20 успешно.

| Метрика | Baseline (opencv) | Post-fix | Δ% |
| --- | ---: | ---: | ---: |
| pipeline_hz process | 15.3 | 10.7 | -30% |
| pipeline_hz thread | 38.5 | 32.9 | -14% |
| p95 pipeline ms process | 128 | 175 | +37% |
| max_ram_gb process | 29.1 | 29.5 | ~0 |
| drop_events (все runs) | 0 | 0 | — |
| lag_ratio opencv process | 2.67 | 2.69 | ~0 |

## Интерпретация

1. **Цель H3 достигнута:** потерь кадров в логах (`drop_events`) нет; `PerfDiag(MpBarrier): pending=50–75 dropped=0` — очереди заполняются, но без drop.
2. **Controller loop Hz снизился** при `QUEUE_SCALE=2`: больший backlog MP увеличивает `pending`, цикл `pipeline.process()` чаще видит `len=0` на drain в том же тике (H2 сохраняется).
3. **Рекомендация для production-bench:** `EVILEYE_MP_QUEUE_SCALE=1`, `EVILEYE_MP_DRAIN_POLL_SEC=0.01`, опционально `EVILEYE_CONTROLLER_BACKPRESSURE=1` — перепроверить E2E и pipeline_hz.
4. **Отдельные YOLO-процессы сохранены** (15 воркеров на poly-videos).

## E2E (90 с active, scale=2)

| Config | e2e_tracker_fps | Примечание |
| --- | ---: | --- |
| process | 20.5 | measure_poly_e2e_fps, 33% unmatched |
| thread | 6.2 | высокий unmatched — метрика требует доработки сопоставления frame_id |

Primary KPI для приёмки — стабильный E2E после настройки scale/backpressure; `pipeline_hz_est` не равен E2E FPS.

## Артефакты (локально, `reports/` в .gitignore)

- `reports/poly_videos_mode_compare/barrier_analysis.md`
- `reports/poly_videos_mode_compare/report.md`
- `reports/poly_videos_mode_compare/baseline_pre_fix/`
