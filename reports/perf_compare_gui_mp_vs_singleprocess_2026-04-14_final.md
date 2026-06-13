# Финальное сравнение с GUI: Multiprocess vs Single-process

- MP лог: `reports/perf_cmp_gui_mp_final_2026-04-14.log`
- SP лог: `reports/perf_cmp_gui_sp_final_2026-04-14.log`

## Ключевые метрики (avg / p95 / max)

| Метрика | Multiprocess (GUI) | Single-process (GUI) | Delta avg (MP-SP) |
| --- | ---: | ---: | ---: |
| Pipeline total ms | 3.02 / 11.50 / 11.50 | 2.40 / 5.60 / 5.60 | +0.62 |
| Sources stage ms | 0.01 / 0.10 / 0.10 | 0.00 / 0.00 / 0.00 | +0.01 |
| Detectors stage ms | 1.23 / 5.40 / 5.40 | 1.28 / 4.90 / 4.90 | -0.05 |
| Trackers stage ms | 1.64 / 10.30 / 10.30 | 0.97 / 2.60 / 2.60 | +0.67 |
| MC trackers stage ms | 0.05 / 0.10 / 0.10 | 0.05 / 0.10 / 0.10 | +0.00 |
| Controller total ms | 5.27 / 17.40 / 17.40 | 3.77 / 7.20 / 7.20 | +1.50 |
| Controller pipeline ms | 3.42 / 12.20 / 12.20 | 2.79 / 6.00 / 6.00 | +0.63 |
| Controller publish ms | 1.52 / 4.90 / 4.90 | 0.65 / 1.00 / 1.00 | +0.86 |
| Controller viz ms | 0.00 / 0.00 / 0.00 | 0.00 / 0.00 / 0.00 | +0.00 |
| ObjectsHandler proc ms | 0.20 / 0.30 / 0.30 | 0.20 / 0.30 / 0.30 | +0.00 |

## Data flow и качество

| Показатель | MP | SP |
| --- | ---: | ---: |
| Pipeline samples | 13 | 13 |
| Controller samples | 13 | 13 |
| Avg detectors output len | 1.15 | 0.85 |
| Avg trackers output len | 0.38 | 0.62 |
| Avg active objects | 1.00 | 1.00 |
| Avg lost objects | 0.00 | 0.14 |
| Warnings | 5 | 5 |
| Errors/Tracebacks | 0 | 0 |
