# Сравнение производительности: Multiprocess vs Single-process

- Дата: `2026-04-14T20:32:02`
- MP лог: `reports/perf_cmp_single_video_multiprocess_after_queue_fix.log`
- SP лог: `reports/perf_cmp_single_video_singleprocess.log`
- Формат метрик `avg / p95 / max` в миллисекундах.

## Pipeline этапы

| Метрика | Multiprocess | Single-process | Delta avg (MP-SP) |
| --- | ---: | ---: | ---: |
| Pipeline total ms | 18.47 / 85.80 / 87.50 | 2.33 / 3.40 / 3.40 | +16.14 |
| Sources stage ms | 0.00 / 0.00 / 0.00 | 0.05 / 0.10 / 0.20 | -0.05 |
| Detectors stage ms | 14.56 / 49.80 / 83.90 | 1.25 / 2.00 / 2.10 | +13.30 |
| Trackers stage ms | 3.73 / 2.30 / 48.60 | 0.82 / 1.40 / 2.00 | +2.92 |
| MC trackers stage ms | 0.03 / 0.10 / 0.10 | 0.07 / 0.10 / 0.10 | -0.04 |

## Controller цикл

| Метрика | Multiprocess | Single-process | Delta avg (MP-SP) |
| --- | ---: | ---: | ---: |
| Controller total ms | 19.51 / 87.10 / 88.50 | 4.42 / 6.50 / 13.10 | +15.10 |
| Controller pipeline ms | 18.97 / 86.60 / 88.00 | 3.68 / 4.00 / 12.70 | +15.29 |
| Controller select ms | 0.28 / 0.50 / 0.50 | 0.46 / 0.90 / 2.70 | -0.18 |
| Controller proc ms | 0.11 / 0.20 / 0.20 | 0.13 / 0.20 / 0.30 | -0.03 |
| Controller publish ms | 0.17 / 0.30 / 0.30 | 0.14 / 0.20 / 0.50 | +0.03 |
| Controller viz ms | 0.00 / 0.00 / 0.00 | 0.00 / 0.00 / 0.00 | +0.00 |

## Поток данных и качество обработки

| Показатель | Multiprocess | Single-process |
| --- | ---: | ---: |
| Pipeline samples | 18 | 13 |
| Controller samples | 18 | 13 |
| Avg detectors output len | 0.39 | 0.77 |
| Avg trackers output len | 0.28 | 0.62 |
| Objects active avg / max | 1.00 / 1 | 1.00 / 1 |
| Objects lost avg / max | 0.00 / 0 | 0.17 / 1 |
| Warnings | 5 | 5 |
| Errors/Tracebacks | 1 | 0 |

## Выводы

- После фиксов узкого места MP-режим ускорился кратно относительно предыдущего состояния (особенно на `detectors` этапе).
- Для данного сценария (1 источник, 1 детектор, 1 трекер, короткий ролик) single-process остаётся быстрее по latency.
- MP-режим остаётся рабочим: объекты детектируются/трекуются и доходят до `ObjectsHandler`.
