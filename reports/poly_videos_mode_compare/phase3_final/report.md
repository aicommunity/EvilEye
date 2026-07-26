# Сравнение poly-videos: process vs thread

## Методика
- Дата отчёта: 2026-05-22T14:31:14
- Платформа: Linux-6.8.0-117-generic-x86_64-with-glibc2.35
- Python: 3.10.12
- 5 прогонов × 180 с на конфиг, headless (`--no-gui --autoclose`)
- Env: `EVILEYE_PERF_DIAG=1`, `EVILEYE_PERF_DIAG_EVERY=30`, `EVILEYE_RESOURCE_STATS_EVERY_SEC=2`, `PYTHONUNBUFFERED=1`
- Bench overlay: `controller.perf_diag=true` (временный JSON, не в git)

## Сводка конфигов

| Capture | Mode | Config |
| --- | --- | --- |
| opencv | process | `configs/poly-videos.json` |
| opencv | thread | `configs/poly-videos-thread.json` |
| gst | process | `configs/poly-videos-gst.json` |
| gst | thread | `configs/poly-videos-gst-thread.json` |

## Стабильность прогонов

| Capture | Mode | Run | Exit | Timeout | Tracebacks | Success |
| --- | --- | ---: | ---: | --- | ---: | --- |
| gst | process | 1 | 0 | нет | 0 | да |
| gst | process | 2 | 0 | нет | 0 | да |
| gst | process | 3 | 0 | нет | 0 | да |
| gst | process | 4 | 0 | нет | 0 | да |
| gst | process | 5 | 0 | нет | 0 | да |
| gst | thread | 1 | -6 | нет | 0 | нет |
| gst | thread | 2 | 0 | нет | 0 | да |
| gst | thread | 3 | 0 | нет | 0 | да |
| gst | thread | 4 | 0 | нет | 0 | да |
| gst | thread | 5 | 0 | нет | 0 | да |
| opencv | process | 1 | 0 | нет | 0 | да |
| opencv | process | 2 | 0 | нет | 0 | да |
| opencv | process | 3 | 0 | нет | 0 | да |
| opencv | process | 4 | 0 | нет | 0 | да |
| opencv | process | 5 | 0 | нет | 0 | да |
| opencv | thread | 1 | 0 | нет | 0 | да |
| opencv | thread | 2 | 0 | нет | 0 | да |
| opencv | thread | 3 | 0 | нет | 0 | да |
| opencv | thread | 4 | 0 | нет | 0 | да |
| opencv | thread | 5 | 0 | нет | 0 | да |

## Временные характеристики (opencv)

### pipeline_hz_est

| Capture | Mode | pipeline_hz_est (mean±std, n) |
| --- | --- | --- |
| opencv | process | 9,86 ± 0,40 |
| opencv | thread | 32,48 ± 3,64 |

### p95_pipeline_ms

| Capture | Mode | p95_pipeline_ms (mean±std, n) |
| --- | --- | --- |
| opencv | process | 184,92 ± 13,31 |
| opencv | thread | 78,78 ± 17,86 |

### max_ram_gb

| Capture | Mode | max_ram_gb (mean±std, n) |
| --- | --- | --- |
| opencv | process | 28,93 ± 0,04 |
| opencv | thread | 11,14 ± 0,17 |

### opencv: thread vs process (pipeline_hz_est)

- thread mean: 32,48
- process mean: 9,86
- Δ% (process vs thread): -69,6%
- Лучший режим (по mean): **thread**


## Временные характеристики (gst)

### pipeline_hz_est

| Capture | Mode | pipeline_hz_est (mean±std, n) |
| --- | --- | --- |
| gst | process | 15,25 ± 1,56 |
| gst | thread | 22,42 ± 2,36 |

### p95_pipeline_ms

| Capture | Mode | p95_pipeline_ms (mean±std, n) |
| --- | --- | --- |
| gst | process | 197,22 ± 18,61 |
| gst | thread | 122,74 ± 16,92 |

### max_ram_gb

| Capture | Mode | max_ram_gb (mean±std, n) |
| --- | --- | --- |
| gst | process | 31,45 ± 0,20 |
| gst | thread | 10,10 ± 0,41 |

### gst: thread vs process (pipeline_hz_est)

- thread mean: 22,42
- process mean: 15,25
- Δ% (process vs thread): -32,0%
- Лучший режим (по mean): **thread**


## E2E tracker FPS (сквозная)

| Config file | e2e_tracker_fps | e2e_p95_ms | pending_unmatched_pct |
| --- | ---: | ---: | ---: |
| `e2e_opencv_process.json` | 29.8724 | 932.83 | 24.45 |
| `e2e_opencv_thread.json` | 9.2639 | 3187.18 | 82.2 |
Снимки не найдены. Запустите `collect_poly_mode_output_snapshot.py`.

## Выводы

### opencv: thread vs process (pipeline_hz_est)

- thread mean: 32,48
- process mean: 9,86
- Δ% (process vs thread): -69,6%
- Лучший режим (по mean): **thread**

### gst: thread vs process (pipeline_hz_est)

- thread mean: 22,42
- process mean: 15,25
- Δ% (process vs thread): -32,0%
- Лучший режим (по mean): **thread**


## Графики

- `reports/poly_videos_mode_compare/phase3_final/plots/pipeline_hz.png`
- `reports/poly_videos_mode_compare/phase3_final/plots/ram_gb.png`

## Приложение
- Каталог: `reports/poly_videos_mode_compare/phase3_final`
- Воспроизведение: `python scripts/run_poly_videos_mode_compare.py`
- Snapshot: `python scripts/collect_poly_mode_output_snapshot.py`
