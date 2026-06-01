# Сравнение производительности с GUI: Multiprocess vs Single-process

- MP лог: `reports/perf_cmp_gui_mp_2026-04-14.log`
- SP лог: `reports/perf_cmp_gui_sp_2026-04-14.log`

## Ключевые метрики (avg / p95 / max)

| Метрика | Multiprocess (GUI) | Single-process (GUI) | Delta avg (MP-SP) |
| --- | ---: | ---: | ---: |
| Pipeline total ms | 9.99 / 50.20 / 50.20 | 1.82 / 2.30 / 2.30 | +8.18 |
| Sources stage ms | 0.00 / 0.00 / 0.00 | 0.00 / 0.00 / 0.00 | +0.00 |
| Detectors stage ms | 8.49 / 48.30 / 48.30 | 0.96 / 1.50 / 1.50 | +7.53 |
| Trackers stage ms | 1.33 / 1.90 / 1.90 | 0.72 / 1.40 / 1.40 | +0.62 |
| MC trackers stage ms | 0.05 / 0.10 / 0.10 | 0.05 / 0.10 / 0.10 | +0.00 |
| Controller total ms | 18.31 / 71.20 / 71.20 | 3.33 / 4.20 / 4.20 | +14.98 |
| Controller pipeline ms | 14.32 / 50.90 / 50.90 | 2.30 / 3.00 / 3.00 | +12.02 |
| Controller publish ms | 3.58 / 20.90 / 20.90 | 0.72 / 1.70 / 1.70 | +2.86 |
| Controller viz ms | 0.00 / 0.00 / 0.00 | 0.00 / 0.00 / 0.00 | +0.00 |
| ObjectsHandler proc ms | 0.23 / 0.30 / 0.30 | 0.19 / 0.20 / 0.20 | +0.05 |

## Data flow и качество

| Показатель | MP | SP |
| --- | ---: | ---: |
| Pipeline samples | 13 | 13 |
| Controller samples | 13 | 13 |
| Avg detectors output len | 0.77 | 0.85 |
| Avg trackers output len | 0.23 | 0.62 |
| Avg active objects | 1.00 | 1.00 |
| Avg lost objects | 0.00 | 0.14 |
| Warnings | 5 | 5 |
| Errors/Tracebacks | 0 | 0 |
