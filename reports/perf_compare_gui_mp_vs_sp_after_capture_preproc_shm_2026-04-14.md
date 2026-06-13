# Сравнение после capture+preprocessing descriptor-path

- MP: `reports/perf_cmp_gui_mp_after_capture_preproc_shm_recheck.log`
- SP: `reports/perf_cmp_gui_sp_after_capture_preproc_shm_recheck.log`

## Latency (avg / p95 / max)

| Метрика | MP | SP | Delta avg (MP-SP) |
| --- | ---: | ---: | ---: |
| Pipeline total ms | 11.41 / 22.10 / 22.10 | 2.86 / 7.10 / 7.10 | +8.55 |
| Detectors stage ms | 10.57 / 20.90 / 20.90 | 1.83 / 5.20 / 5.20 | +8.74 |
| Trackers stage ms | 0.63 / 0.90 / 0.90 | 0.79 / 1.60 / 1.60 | -0.16 |
| Controller total ms | 13.03 / 24.20 / 24.20 | 4.34 / 9.30 / 9.30 | +8.69 |
| Controller pipeline ms | 11.77 / 22.80 / 22.80 | 3.32 / 7.70 / 7.70 | +8.45 |
| Controller publish ms | 0.97 / 4.50 / 4.50 | 0.69 / 1.20 / 1.20 | +0.28 |

## Throughput/Freshness (updates per PerfDiag window)

| Метрика | MP | SP |
| --- | ---: | ---: |
| DetectorsIn updates/window | 19.29 | 19.85 |
| DetectorsIn repeats/window | 0.00 | 0.00 |
| TrackersIn updates/window | 18.57 | 16.00 |
| TrackersOut updates/window | 10.07 | 12.77 |
| TrackersOut repeats/window | 0.00 | 0.00 |

## Дополнительно

| Показатель | MP | SP |
| --- | ---: | ---: |
| Pipeline samples | 14 | 13 |
| Controller samples | 14 | 13 |
| Avg detectors output len | 1.00 | 0.85 |
| Avg trackers output len | 0.36 | 0.77 |
| Warnings | 5 | 5 |
| Errors/Tracebacks | 0 | 0 |
