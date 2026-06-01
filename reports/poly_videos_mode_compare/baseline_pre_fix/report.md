# Сравнение poly-videos: process vs thread

## Методика
- Дата отчёта: 2026-05-22T00:29:48
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
| opencv | process | 15,34 ± 1,10 |
| opencv | thread | 38,46 ± 4,49 |

### p95_pipeline_ms

| Capture | Mode | p95_pipeline_ms (mean±std, n) |
| --- | --- | --- |
| opencv | process | 127,76 ± 13,49 |
| opencv | thread | 61,68 ± 16,27 |

### max_ram_gb

| Capture | Mode | max_ram_gb (mean±std, n) |
| --- | --- | --- |
| opencv | process | 29,13 ± 0,06 |
| opencv | thread | 10,49 ± 1,31 |

### opencv: thread vs process (pipeline_hz_est)

- thread mean: 38,46
- process mean: 15,34
- Δ% (process vs thread): -60,1%
- Лучший режим (по mean): **thread**


## Временные характеристики (gst)

### pipeline_hz_est

| Capture | Mode | pipeline_hz_est (mean±std, n) |
| --- | --- | --- |
| gst | process | 20,51 ± 1,49 |
| gst | thread | 22,87 ± 4,86 |

### p95_pipeline_ms

| Capture | Mode | p95_pipeline_ms (mean±std, n) |
| --- | --- | --- |
| gst | process | 129,14 ± 13,49 |
| gst | thread | 84,38 ± 25,04 |

### max_ram_gb

| Capture | Mode | max_ram_gb (mean±std, n) |
| --- | --- | --- |
| gst | process | 32,28 ± 0,43 |
| gst | thread | 11,07 ± 1,04 |

### gst: thread vs process (pipeline_hz_est)

- thread mean: 22,87
- process mean: 20,51
- Δ% (process vs thread): -10,3%
- Лучший режим (по mean): **thread**


## Выходные данные (snapshot)

| Slug | mc_emit_rate | sticky_tracks_mean | objects | has_data |
| --- | ---: | ---: | ---: | --- |
| poly-videos_gst_process | 0.2333 | 2.42 | 5 | True |
| poly-videos_gst_thread | 0.3167 | 3.81 | 5 | True |
| poly-videos_opencv_process | 0.1167 | 1.53 | 5 | True |
| poly-videos_opencv_thread | 0.2667 | 3.53 | 5 | True |

## Выводы

### opencv: thread vs process (pipeline_hz_est)

- thread mean: 38,46
- process mean: 15,34
- Δ% (process vs thread): -60,1%
- Лучший режим (по mean): **thread**

### gst: thread vs process (pipeline_hz_est)

- thread mean: 22,87
- process mean: 20,51
- Δ% (process vs thread): -10,3%
- Лучший режим (по mean): **thread**


## Графики

- `reports/poly_videos_mode_compare/plots/pipeline_hz.png`
- `reports/poly_videos_mode_compare/plots/ram_gb.png`

## Приложение
- Каталог: `reports/poly_videos_mode_compare`
- Воспроизведение: `python scripts/run_poly_videos_mode_compare.py`
- Snapshot: `python scripts/collect_poly_mode_output_snapshot.py`
