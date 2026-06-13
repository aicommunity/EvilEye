# Запуск тестов производительности EvilEye (Linux benchmark)

Руководство по воспроизведению эксперимента сравнения **однопроцессного** (`thread`) и **мультипроцессного** (`process`) режимов на сценарии **полный пайплайн** (`full`) со схемой **отдельный процесс на камеру** для захвата, YOLO и трекера (`process_full`).

Методика и расшифровка метрик — в [`diploma_benchmark_methodology.md`](diploma_benchmark_methodology.md).

---

## Содержание

1. [Требования](#1-требования)
2. [Что измеряется](#2-что-измеряется)
3. [Быстрый старт](#3-быстрый-старт)
4. [Полный пайплайн по шагам](#4-полный-пайплайн-по-шагам)
5. [Пересборка отчётов без повторного прогона](#5-пересборка-отчётов-без-повторного-прогона)
6. [Структура каталогов результатов](#6-структура-каталогов-результатов)
7. [Переменные окружения](#7-переменные-окружения)
8. [Отладка: один прогон](#8-отладка-один-прогон)
9. [Типичные проблемы](#9-типичные-проблемы)
10. [Чего не использовать](#10-чего-не-использовать)

---

## 1. Требования

- **ОС:** Linux (прогоны рассчитаны на машину с GPU; на Windows можно только просматривать уже собранные артефакты).
- **Python:** venv в корне репозитория.
- **Зависимости:** `pip install -e . psutil matplotlib`
- **Видео:** файлы из `configs/multi_videos.json` (каталог `videos/`).
- **GPU-метрики:** `nvidia-smi` в PATH.
- **Headless:** `QT_QPA_PLATFORM=offscreen` (выставляется в скрипте автоматически).

```bash
cd /path/to/EvilEye
python3 -m venv venv
source venv/bin/activate
pip install -e . psutil matplotlib

ls videos/

chmod +x scripts/run_linux_perf_matrix_per_camera_mp.sh
```

---

## 2. Что измеряется

Для каждой комбинации **1–4 камеры** × **CPU / GPU** × **thread / process** запускается один и тот же полный пайплайн из `configs/multi_videos.json`:

- **thread** — захват, YOLO и трекер в одном процессе Python;
- **process** — для каждой камеры отдельные процессы захвата, детектора и трекера.

«Камера» — видеофайл с зацикливанием; при нехватке роликов один файл дублируется. GUI, запись на диск и БД отключены.

Результаты: `reports/linux_perf_matrix_mp_per_camera/`, сводный каталог для работы — `diploma_report/`.

---

## 3. Быстрый старт

Одна команда выполняет весь цикл: конфиги → прогоны → CSV/графики → сводка → `diploma_report/`.

```bash
PYTHON_BIN=venv/bin/python \
BASE_CONFIG=configs/multi_videos.json \
DEVICES="cuda:0 cpu" \
SCENARIOS="full" \
LAYOUTS="process_full" \
TARGET_FPS=120 \
DURATION_SEC=180 \
WARMUP_DURATION_SEC=30 \
PERF_EVERY=30 \
SAMPLE_INTERVAL_SEC=2 \
bash scripts/run_linux_perf_matrix_per_camera_mp.sh \
  2>&1 | tee reports/linux_perf_matrix_mp_per_camera/run.log
```

**Объём:** 2 устройства × 4 камеры × 2 режима = **16 основных прогонов** + короткий warmup. Время — несколько часов.

**Опционально** — нормализованные графики CPU (шкала 0–100%, 32 логических ядра):

```bash
python scripts/generate_normalized_cpu_full_plot.py
```

**Готовые артефакты:**

```text
reports/linux_perf_matrix_mp_per_camera/diploma_report/
```

---

## 4. Полный пайплайн по шагам

Скрипт `run_linux_perf_matrix_per_camera_mp.sh` вызывает цепочку ниже. То же можно запускать **вручную** для отладки.

### Подготовка конфигов

```bash
python scripts/prepare_linux_perf_matrix.py \
  --base-config configs/multi_videos.json \
  --out-dir reports/linux_perf_matrix_mp_per_camera/configs \
  --results-root reports/linux_perf_matrix_mp_per_camera/results \
  --max-cameras 4 \
  --repeat-cameras \
  --no-shared-detector-pool \
  --target-fps 120 \
  --devices cuda:0 cpu \
  --scenarios full \
  --layouts process_full
```

**Что делает:** строит пары `bench_NNcam_thread.json` / `bench_NNcam_process.json`, manifest-ы по группам и `matrix_manifest.json`.

### Прогоны benchmark

```bash
python scripts/run_multiprocessing_benchmark.py \
  --manifest reports/linux_perf_matrix_mp_per_camera/configs/cpu/full/process_full/manifest.json \
  --out-dir reports/linux_perf_matrix_mp_per_camera/results/cpu/full/process_full \
  --camera-counts 1 2 3 4 \
  --modes thread process \
  --duration-sec 180 \
  --timeout-sec 900 \
  --duration-hard-stop \
  --duration-stop-grace-sec 30 \
  --sample-interval-sec 2 \
  --perf-every 30 \
  --no-autoclose \
  --python venv/bin/python
```

**Что делает:**

- запускает `python -m evileye.process` с `EVILEYE_PERF_DIAG=1`;
- пишет **логи** (`logs/NNcam_thread.log`) со строками `PerfDiag(...)` и `FPS=...`;
- пишет **сэмплы ресурсов** (`samples/NNcam_thread.csv`): CPU %, RAM, GPU;
- сохраняет `run_summary.json`.

Перед основным прогоном orchestrator делает **warmup** (~30 с, 1 камера) в каталог `*_warmup/`.

### Рендер группы (CSV + графики)

```bash
python scripts/render_multiprocessing_benchmark_report.py \
  --out-dir reports/linux_perf_matrix_mp_per_camera/results/cpu/full/process_full \
  --warmup-windows 1
```

**Что делает:**

- читает **логи** (приоритет над устаревшим CSV);
- считает метрики: захват, обнаружение, отслеживание, визуализация, p95, CPU/RAM/GPU;
- записывает `results.csv` и bar-графики в `plots/` (thread vs process).

**Важно:** для однопроцессного CPU-режима «Обнаружение» берётся из `PerfDiag(TrackersIn)`, но если счётчик занижен (много `repeats`), парсер переключается на `PerfDiag(Pipeline): detectors=...ms(len=...)`. Без этого шага в CSV могут остаться аномальные ~0.15 кадр/с.

### Сводная матрица

```bash
python scripts/render_linux_perf_matrix_report.py \
  --matrix-manifest reports/linux_perf_matrix_mp_per_camera/configs/matrix_manifest.json \
  --out-dir reports/linux_perf_matrix_mp_per_camera/summary \
  --warmup-windows 1
```

**Что делает:** объединяет все группы → `summary.csv`, `speedup.csv`, графики ускорения `plots/speedup_*.png`.


### Нормализованный CPU % (опционально)

```bash
python scripts/generate_normalized_cpu_full_plot.py
```

**Что делает:** строит `cpu_percent.png` в шкале 0–100% (100% = 32 логических ядра) в `diploma_report/normalized_plots/`.

---

## Пересборка отчётов без повторного прогона

Если **логи уже есть**, можно обновить CSV и графики после правок парсера:

```bash
python scripts/render_multiprocessing_benchmark_report.py \
  --out-dir reports/linux_perf_matrix_mp_per_camera/results/cpu/full/process_full \
  --warmup-windows 1

python scripts/generate_mp_per_camera_corrected_plots.py

python scripts/render_linux_perf_matrix_report.py \
  --matrix-manifest reports/linux_perf_matrix_mp_per_camera/configs/matrix_manifest.json \
  --out-dir reports/linux_perf_matrix_mp_per_camera/summary \
  --warmup-windows 1

python scripts/bundle_linux_perf_matrix_report.py \
  --matrix-manifest reports/linux_perf_matrix_mp_per_camera/configs/matrix_manifest.json \
  --summary-dir reports/linux_perf_matrix_mp_per_camera/summary \
  --bundle-dir reports/linux_perf_matrix_mp_per_camera/diploma_report

python scripts/generate_normalized_cpu_full_plot.py
```

**Без каталога `logs/`** пересчёт невозможен — останутся старые значения из `results.csv`.

---

## Структура каталогов результатов

```text
reports/linux_perf_matrix_mp_per_camera/
├── configs/
│   ├── matrix_manifest.json
│   └── cpu/full/process_full/
│       ├── manifest.json
│       └── bench_01cam_thread.json
├── results/
│   └── cpu/full/process_full/
│       ├── logs/01cam_thread.log
│       ├── samples/01cam_thread.csv
│       ├── run_summary.json
│       ├── results.csv
│       └── plots/
├── summary/
│   ├── summary.csv
│   ├── speedup.csv
│   └── plots/speedup_cpu_full_process_full.png

```

### Столбцы `results.csv`

| Столбец | Источник |
|---|---|
| Захват, кадры/с | `FPS=...` или `PerfDiag(DetectorsIn)` |
| Обнаружение, кадры/с | `PerfDiag(TrackersIn)` или fallback `PerfDiag(Pipeline) detectors=...` |
| Отслеживание, кадры/с | `PerfDiag(TrackersOut)` или fallback по стадии `trackers` |
| Визуализация, кадры/с | `PerfDiag: loop=..., frames=...` |
| p95 цикла, мс | перцентиль `PerfDiag(Pipeline) total=...ms` |
| CPU, % | среднее из `samples/*.csv` |
| RAM / GPU | из samples и nvidia-smi |

---

## Переменные окружения

Передаются в `run_linux_perf_matrix_per_camera_mp.sh`:

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `PYTHON_BIN` | `venv/bin/python` | Интерпретатор |
| `BASE_CONFIG` | `configs/multi_videos.json` | Базовый конфиг |
| `MAX_CAMERAS` | `4` | Число камер в матрице |
| `TARGET_FPS` | `120` | Целевой FPS в конфиге |
| `DURATION_SEC` | `180` | Длительность основного прогона |
| `WARMUP_DURATION_SEC` | `30` | Длительность warmup |
| `TIMEOUT_SEC` | `900` | Жёсткий таймаут процесса |
| `PERF_EVERY` | `30` | Период строк PerfDiag (такты) |
| `SAMPLE_INTERVAL_SEC` | `2` | Интервал сэмплов CPU/RAM/GPU |
| `DEVICES` | `cuda:0 cpu` | Устройства через пробел |
| `SCENARIOS` | `full` | Сценарий пайплайна |
| `LAYOUTS` | `process_full` | Схема multiprocessing |
| `WARMUP` | `1` | Короткий прогрев перед основным |
| `RENDER_EACH` | `1` | Рендер CSV после каждой группы |
| `ALLOW_MISSING` | `0` | `1` — не падать при отсутствии видеофайлов |

Для CPU-прогонов скрипт выставляет `CUDA_VISIBLE_DEVICES=""`.

---

## Отладка: один прогон

```bash
python scripts/run_multiprocessing_benchmark.py \
  --manifest reports/linux_perf_matrix_mp_per_camera/configs/cpu/full/process_full/manifest.json \
  --out-dir /tmp/bench_smoke \
  --camera-counts 1 \
  --modes thread \
  --duration-sec 60 \
  --perf-every 30 \
  --no-autoclose \
  --python venv/bin/python

python scripts/render_multiprocessing_benchmark_report.py \
  --out-dir /tmp/bench_smoke \
  --warmup-windows 0
```

Проверка парсера логов:

```bash
python -m pytest tests/unit/scripts/test_render_multiprocessing_benchmark_report.py -v
```

## Связанные документы

- [`diploma_benchmark_methodology.md`](diploma_benchmark_methodology.md) — методика, PerfDiag, расшифровка метрик
