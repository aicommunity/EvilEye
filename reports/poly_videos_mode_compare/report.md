# Сравнение poly-videos: process vs thread

## Методика
- Дата отчёта: 2026-05-22T11:30:18
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

## Аудит параметров (config_audit.md)

# Аудит конфигов poly-videos (process vs thread)

## Сравниваемые файлы

| Capture | Mode | Config |
| --- | --- | --- |
| opencv | process | `configs/poly-videos.json` |
| opencv | thread | `configs/poly-videos-thread.json` |
| gst | process | `configs/poly-videos-gst.json` |
| gst | thread | `configs/poly-videos-gst-thread.json` |

## Пары process/thread

### opencv: `configs/poly-videos.json` vs `configs/poly-videos-thread.json`
- Всего отличий: **13**
- Неожиданных (кроме execution_mode): **0**

Неожиданных отличий нет (только `execution_mode`).

### gst: `configs/poly-videos-gst.json` vs `configs/poly-videos-gst-thread.json`
- Всего отличий: **13**
- Неожиданных (кроме execution_mode): **0**

Неожиданных отличий нет (только `execution_mode`).

## Видеофайлы

- `configs/poly-videos.json`: **OK**
- `configs/poly-videos-thread.json`: **OK**
- `configs/poly-videos-gst.json`: **OK**
- `configs/poly-videos-gst-thread.json`: **OK**

## OpenCV vs GStreamer (справочно)

Между `poly-videos*.json` и `poly-videos-gst*.json` ожидаются отличия `type`, `apiPreference`, `gstreamer_*` и пути захвата — это разные backend.

- Число отличий opencv vs gst (базовые process-конфиги): **269**

## Preflight

- `validate_json_configs.py`: **OK**


## Стабильность прогонов

| Capture | Mode | Run | Exit | Timeout | Tracebacks | Success |
| --- | --- | ---: | ---: | --- | ---: | --- |
| gst | process | 1 | 0 | нет | 0 | да |
| gst | process | 2 | 0 | нет | 0 | да |
| gst | process | 3 | 0 | нет | 0 | да |
| gst | process | 4 | 0 | нет | 0 | да |
| gst | process | 5 | 0 | нет | 0 | да |
| gst | thread | 1 | 0 | нет | 0 | да |
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
| opencv | process | 10,87 ± 0,81 |
| opencv | thread | 35,01 ± 7,15 |

### p95_pipeline_ms

| Capture | Mode | p95_pipeline_ms (mean±std, n) |
| --- | --- | --- |
| opencv | process | 159,14 ± 15,52 |
| opencv | thread | 66,66 ± 17,53 |

### max_ram_gb

| Capture | Mode | max_ram_gb (mean±std, n) |
| --- | --- | --- |
| opencv | process | 28,86 ± 0,02 |
| opencv | thread | 11,25 ± 0,11 |

### opencv: thread vs process (pipeline_hz_est)

- thread mean: 35,01
- process mean: 10,87
- Δ% (process vs thread): -69,0%
- Лучший режим (по mean): **thread**


## Временные характеристики (gst)

### pipeline_hz_est

| Capture | Mode | pipeline_hz_est (mean±std, n) |
| --- | --- | --- |
| gst | process | 14,54 ± 1,24 |
| gst | thread | 24,96 ± 1,61 |

### p95_pipeline_ms

| Capture | Mode | p95_pipeline_ms (mean±std, n) |
| --- | --- | --- |
| gst | process | 192,38 ± 20,25 |
| gst | thread | 61,58 ± 9,17 |

### max_ram_gb

| Capture | Mode | max_ram_gb (mean±std, n) |
| --- | --- | --- |
| gst | process | 31,55 ± 0,09 |
| gst | thread | 10,41 ± 0,76 |

### gst: thread vs process (pipeline_hz_est)

- thread mean: 24,96
- process mean: 14,54
- Δ% (process vs thread): -41,7%
- Лучший режим (по mean): **thread**


## E2E tracker FPS (сквозная)

| Config file | e2e_tracker_fps | e2e_p95_ms | pending_unmatched_pct |
| --- | ---: | ---: | ---: |
| `e2e_opencv_process.json` | 29.8204 | 900.36 | 23.03 |
| `e2e_opencv_thread.json` | 9.2169 | 3185.48 | 82.32 |

## Выходные данные (snapshot)

| Slug | mc_emit_rate | sticky_tracks_mean | objects | has_data |
| --- | ---: | ---: | ---: | --- |
| poly-videos_gst_process | 0.1833 | 1.03 | 5 | True |
| poly-videos_gst_thread | 0.175 | 2.18 | 0 | True |
| poly-videos_opencv_process | 0.0667 | 0.6 | 0 | True |
| poly-videos_opencv_thread | 0.2 | 2.87 | 0 | True |

## Выводы

### opencv: thread vs process (pipeline_hz_est)

- thread mean: 35,01
- process mean: 10,87
- Δ% (process vs thread): -69,0%
- Лучший режим (по mean): **thread**

### gst: thread vs process (pipeline_hz_est)

- thread mean: 24,96
- process mean: 14,54
- Δ% (process vs thread): -41,7%
- Лучший режим (по mean): **thread**


## Графики

- `reports/poly_videos_mode_compare/plots/pipeline_hz.png`
- `reports/poly_videos_mode_compare/plots/ram_gb.png`

## Приложение
- Каталог: `reports/poly_videos_mode_compare`
- Воспроизведение: `python scripts/run_poly_videos_mode_compare.py`
- Snapshot: `python scripts/collect_poly_mode_output_snapshot.py`
