# Методика benchmark и пересчёта метрик производительности

Единая инструкция по воспроизведению измерений thread vs process в EvilEye: подготовка окружения, выбор сценария, запуск скриптов, интерпретация артефактов и gate-проверки.

**См. также:** [multiprocessing_benchmark.md](multiprocessing_benchmark.md) (классический 3-шаговый bench), [mp_fps_phase3_summary.md](mp_fps_phase3_summary.md) (итоги тюнинга F2).

---

## 1. Предварительные условия

### Окружение

```bash
cd /path/to/EvilEye
python3 -m venv venv
source venv/bin/activate
pip install -e .
evileye deploy-samples   # видео в videos/
```

- **Интерпретатор:** `PYTHON_BIN=venv/bin/python` (дочерние процессы бенчмарка должны использовать тот же venv).
- **Headless GUI:** `export QT_QPA_PLATFORM=offscreen`
- **Диагностика:** runner-ы выставляют `EVILEYE_PERF_DIAG=1`, `EVILEYE_PERF_DIAG_EVERY=30` автоматически или через env.
- **GPU:** для CUDA-прогонов нужен `nvidia-smi`; для CPU-only — `CUDA_VISIBLE_DEVICES=""`.
- **Модели:** YOLO в `models/` или auto-download при первом запуске.

### Проверка готовности

```bash
test -f videos/planes_sample.mp4 || evileye deploy-samples
venv/bin/python -c "import evileye; print('ok')"
```

Если видео из конфига недоступны, для генерации шаблонов без проверки путей: `ALLOW_MISSING=1` (см. §8).

---

## 2. Какой сценарий выбрать

| Цель | Сценарий | Команда / скрипт | Артефакты |
|------|----------|------------------|-----------|
| Диплом, полная матрица CPU+GPU, per-camera MP | **A** | `./scripts/run_linux_perf_matrix_per_camera_mp.sh` | `reports/linux_perf_matrix_mp_per_camera/` |
| Расширенная матрица (все сценарии × layouts) | **F** | `./scripts/run_linux_perf_matrix.sh` | `reports/linux_perf_matrix/` |
| Быстрое сравнение cap+det в process | **B** | prepare → run → render (см. §4) | `reports/bench_multiprocessing*/` |
| MP refactor gate после изменений hot path | **C** | E2E + soak (см. §5) | `reports/mp_refactor_gate/` |
| Тюнинг env F0–F7 | **D** | `./scripts/run_e2e_fps_matrix.sh` | `reports/poly_videos_mode_compare/experiments/e2e_fps_matrix/` |
| Регрессия IPC / shutdown / KPI | **E** | `run_ipc_kpi_gate.py` (см. §6) | `reports/ipc_kpi_gate_*/` |

**Оценка времени:**

| Сценарий | Длительность (ориентир) |
|----------|-------------------------|
| A (полная матрица) | ~4 группы × 8 прогонов × 180 s ≈ **2–4 ч** (+ warmup) |
| B (1 layout, 4 камеры) | 8 прогонов × 60 s ≈ **15–20 мин** |
| C E2E | ~5 мин (90 s × 2 режима) |
| C soak | **30 мин** (по умолчанию) |
| E KPI gate | ~2 × 45 s ≈ **2 мин** |

---

## 3. Сценарий A — Linux perf matrix per camera (диплом)

**Схема:** capture, detector и tracker — в **отдельных процессах**, по одному процессу на камеру; сравнение `thread` vs `process` для 1–4 камер на CPU и GPU.

### One-liner

```bash
export QT_QPA_PLATFORM=offscreen
./scripts/run_linux_perf_matrix_per_camera_mp.sh
```

### Переменные окружения runner-а

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `PYTHON_BIN` | `venv/bin/python` | Интерпретатор |
| `BASE_CONFIG` | `configs/multi_videos.json` | Базовый конфиг |
| `MATRIX_ROOT` | `reports/linux_perf_matrix_mp_per_camera` | Корень артефактов |
| `MAX_CAMERAS` | `4` | Точки 1–4 камеры |
| `TARGET_FPS` | `120` | Лимит FPS источников/visualizer |
| `DURATION_SEC` | `180` | Стационарная фаза |
| `WARMUP_DURATION_SEC` | `30` | Прогрев (1 cam) |
| `DEVICES` | `cuda:0 cpu` | Устройства детектора |
| `SCENARIOS` | `tracking full` | Подмножество сценариев |
| `LAYOUTS` | `process_full` | Layout MP |
| `WARMUP` | `1` | Включить прогрев |
| `RENDER_EACH` | `1` | Отчёт после каждой группы |

Пример ускоренного smoke (1 камера, 30 s):

```bash
DURATION_SEC=30 MAX_CAMERAS=1 DEVICES=cpu SCENARIOS=full \
  ./scripts/run_linux_perf_matrix_per_camera_mp.sh
```

### Цепочка скриптов (эквивалент one-liner)

```bash
# 1. Генерация конфигов и matrix_manifest.json
venv/bin/python scripts/prepare_linux_perf_matrix.py \
  --base-config configs/multi_videos.json \
  --out-dir reports/linux_perf_matrix_mp_per_camera/configs \
  --results-root reports/linux_perf_matrix_mp_per_camera/results \
  --max-cameras 4 --repeat-cameras \
  --no-shared-detector-pool \
  --target-fps 120 --num-detection-threads 1 \
  --devices cpu cuda:0 \
  --scenarios tracking full \
  --layouts process_full

# 2. Прогоны (для каждой группы из manifest)
venv/bin/python scripts/run_multiprocessing_benchmark.py \
  --manifest reports/linux_perf_matrix_mp_per_camera/configs/cpu/full/process_full/manifest.json \
  --out-dir reports/linux_perf_matrix_mp_per_camera/results/cpu/full/process_full \
  --camera-counts 1 2 3 4 --modes thread process \
  --duration-sec 180 --timeout-sec 900 \
  --duration-hard-stop --duration-stop-grace-sec 30 \
  --sample-interval-sec 2 --perf-every 30 \
  --no-autoclose --python venv/bin/python

# 3. Отчёт по одной группе
venv/bin/python scripts/render_multiprocessing_benchmark_report.py \
  --out-dir reports/linux_perf_matrix_mp_per_camera/results/cpu/full/process_full \
  --warmup-windows 1

# 4. Сводка по всей матрице
venv/bin/python scripts/render_linux_perf_matrix_report.py \
  --matrix-manifest reports/linux_perf_matrix_mp_per_camera/configs/matrix_manifest.json \
  --out-dir reports/linux_perf_matrix_mp_per_camera/summary \
  --warmup-windows 1

# 5. Сборка каталога для отчёта
venv/bin/python scripts/bundle_linux_perf_matrix_report.py \
  --matrix-manifest reports/linux_perf_matrix_mp_per_camera/configs/matrix_manifest.json \
  --results-root reports/linux_perf_matrix_mp_per_camera/results \
  --summary-dir reports/linux_perf_matrix_mp_per_camera/summary \
  --bundle-dir reports/linux_perf_matrix_mp_per_camera/diploma_report \
  --warmup-windows 1
```

### Выходные артефакты

```
reports/linux_perf_matrix_mp_per_camera/
├── configs/matrix_manifest.json
├── results/{cpu,cuda_0}/{tracking,full}/process_full/
│   ├── results.csv, report.md, run_summary.json
│   ├── samples/*.csv, logs/*.log, plots/*.png
├── summary/summary.csv, speedup.csv, report.md, plots/
└── diploma_report/          # готовая сборка для пояснительной записки
    ├── README.md, report.md, summary.csv, speedup.csv
    ├── tables/*_results.csv
    └── plots/<группа>/*.png
```

### Критерии валидности прогона

Прогон **не включается** в итоговый вывод (`Можно использовать в отчете = нет`), если:

- exit code ≠ 0, timeout, traceback в логе;
- превышены пороги CPU/GPU/RAM в `render_linux_perf_matrix_report.py` (`--max-cpu-percent`, `--max-gpu-percent`, `--max-ram-gb`).

---

## 4. Сценарий B — Классический bench (cap + YOLO pool)

Подробности — в [multiprocessing_benchmark.md](multiprocessing_benchmark.md). Краткая последовательность:

```bash
# Подготовка
venv/bin/python scripts/prepare_multiprocessing_benchmark.py \
  --base-config configs/multi_videos.json \
  --max-cameras 4 --repeat-cameras \
  --out-dir reports/bench_multiprocessing/configs_pool_cap_det_process \
  --shared-detector-pool \
  --capture-and-detector-process-only \
  --num-detection-threads 1 --target-fps 30

# Прогоны
venv/bin/python scripts/run_multiprocessing_benchmark.py \
  --manifest reports/bench_multiprocessing/configs_pool_cap_det_process/manifest.json \
  --out-dir reports/bench_multiprocessing_fps30_pool_cap_det_process \
  --camera-counts 1 2 3 4 --modes thread process \
  --duration-sec 60 --timeout-sec 480 --sample-interval-sec 2 \
  --perf-every 30 --no-autoclose --python venv/bin/python

# Отчёт
venv/bin/python scripts/render_multiprocessing_benchmark_report.py \
  --out-dir reports/bench_multiprocessing_fps30_pool_cap_det_process
```

---

## 5. Сценарий C — MP refactor gate

Проверка после изменений MP hot path (detector/tracker bridge, backpressure, pipeline drain).

### Env (профиль F2, production defaults)

```bash
export EVILEYE_MP_QUEUE_SCALE=1
export EVILEYE_MP_DRAIN_POLL_SEC=0.01
export EVILEYE_CONTROLLER_BACKPRESSURE=soft
```

### E2E 90 s

```bash
mkdir -p reports/mp_refactor_gate

# Process mode
venv/bin/python scripts/measure_poly_e2e_fps.py \
  --config configs/poly-videos.json \
  --warmup-sec 25 --active-sec 90 \
  --env-note gate_process \
  | tee reports/mp_refactor_gate/e2e_process.json

# Thread mode (baseline)
venv/bin/python scripts/measure_poly_e2e_fps.py \
  --config configs/poly-videos-thread.json \
  --warmup-sec 25 --active-sec 90 \
  --env-note gate_thread \
  | tee reports/mp_refactor_gate/e2e_thread.json
```

**Gate KPI:**

| Метрика | Цель |
|---------|------|
| `e2e_tracker_fps` (process) | ≥ 25 (ориентир; исторически ~28) |
| `e2e_ratio` = process/thread | **≥ 3.0** |
| `staleness_in_band` | `true` (mean ∈ [5.9, 6.5]) |
| `drop_events` (MpBarrier) | 0 |

### Memory soak 30 min

```bash
SOAK_LOG=reports/mp_refactor_gate/soak_mp_rss.log \
  ./scripts/soak_mp_memory.sh configs/poly-videos.json
```

**Gate:** RSS после прогрева **плоский** (рост < 10% за 30 min). Переменные: `SOAK_DURATION_SEC`, `SOAK_RSS_INTERVAL_SEC`.

### Шаблон summary

Зафиксируйте результаты в `reports/mp_refactor_gate/e2e_gate_summary.md` (см. существующий пример от 2026-05-22).

---

## 6. Сценарий D — E2E FPS matrix (тюнинг env)

```bash
./scripts/run_e2e_fps_matrix.sh all    # F0–F7, долго
./scripts/run_e2e_fps_matrix.sh F2     # только winner-профиль

venv/bin/python scripts/compare_poly_e2e_fps_matrix.py \
  --matrix-dir reports/poly_videos_mode_compare/experiments/e2e_fps_matrix \
  --write-winner

./scripts/run_phase3_winner_bench.sh
```

Итоги и интерпретация: [mp_fps_phase3_summary.md](mp_fps_phase3_summary.md).

---

## 7. Сценарий E — KPI gate (IPC / shutdown)

```bash
venv/bin/python scripts/run_ipc_kpi_gate.py \
  --profile configs/kpi_gate_profile.json
```

Профиль задаёт конфиги и пороги (`configs/kpi_gate_profile.json`):

- `single_video_multiprocess.json`, `poly-videos-gst.json`
- `max_errors=0`, `max_tracebacks=0`, `max_stop_timeouts=0`, `max_force_kills=0`
- `max_p95_pipeline_ms`, `max_rss_mb`, `timeout_sec`

Unit-тест gate-логики:

```bash
pytest tests/unit/scripts/test_benchmark_ipc_kpi_gate.py -q
```

---

## 8. Сценарий F — Расширенная Linux perf matrix

Полная матрица: все сценарии (`capture`, `detection`, `tracking`, `visualization`, `full`) × layouts (`process_detector`, `process_capture_detector`, `process_full`).

```bash
./scripts/run_linux_perf_matrix.sh
```

Параметры аналогичны сценарию A, но `MATRIX_ROOT=reports/linux_perf_matrix`, `TARGET_FPS=30`, `DURATION_SEC=90` по умолчанию. **Значительно дольше**, чем per-camera MP.

---

## 9. Справочник метрик

### Bench runner (`run_multiprocessing_benchmark.py` → CSV)

| Метрика в отчёте | Источник | Описание |
|------------------|----------|----------|
| Захват, кадры/с | `PerfDiag` / `FPS=` в логах capture | Средний FPS источников |
| Обнаружение, кадры/с | `PerfDiag(Pipeline)` stage detector | Пропускная способность детектора |
| Отслеживание, кадры/с | stage tracker | Пропускная способность трекера |
| Визуализация, кадры/с | stage visualizer / publish | Частота визуализации |
| p95 цикла, мс | controller loop | 95-й перцентиль полного цикла |
| CPU, % / RAM, ГБ | psutil по дереву процессов | Системные метрики |
| GPU-RAM, ГБ / GPU, % | nvidia-smi | Только при наличии GPU |
| Ошибки / Traceback | парсинг лога | Признак невалидного прогона |

**Ускорение:** `FPS_process / FPS_thread` для пар с одинаковым числом камер.

**Warmup:** первое диагностическое окно отбрасывается (`--warmup-windows 1` по умолчанию в matrix runner).

### E2E (`measure_poly_e2e_fps.py`)

| Метрика | Описание |
|---------|----------|
| `e2e_tracker_fps` | Уникальные пары `(source_id, frame_id)` на выходе trackers за active-фазу / сек |
| `mean_staleness_frames` | Средняя «свежесть» кадра (source frame → tracker output) |
| `staleness_in_band` | `true` если mean ∈ [5.9, 6.5] |
| `e2e_ratio` | process_fps / thread_fps (считается вручную или compare-скриптами) |

### Не путать

| Метрика | Что измеряет |
|---------|--------------|
| `pipeline_hz_est` | Частота вызова `pipeline.process()` в controller |
| `e2e_tracker_fps` | Сквозная пропускная способность до выхода tracker |

В MP-режиме `pipeline_hz_est` **не равен** E2E FPS.

---

## 10. Частичный перезапуск и отладка

```bash
# Только 2 камеры, только process
venv/bin/python scripts/run_multiprocessing_benchmark.py \
  --manifest <path/to/manifest.json> \
  --out-dir <result_dir> \
  --camera-counts 2 --modes process \
  --duration-sec 60 --no-autoclose --python venv/bin/python

# Без промежуточных графиков в matrix runner
RENDER_EACH=0 ./scripts/run_linux_perf_matrix_per_camera_mp.sh

# Конфиги без проверки видео
ALLOW_MISSING=1 ./scripts/run_linux_perf_matrix_per_camera_mp.sh

# Poly mode compare (5×180 s)
python scripts/run_poly_videos_mode_compare.py --timeout-sec 180 --runs-per-config 5
python scripts/analyze_poly_mp_barriers.py
```

**Где смотреть при проблемах:**

- `results/*/logs/*.log` — traceback, MpBarrier, PerfDiag
- `results/*/samples/*.csv` — временные ряды CPU/RAM/FPS
- `results/*/run_summary.json` — exit codes, duration, errors

---

## 11. Unit-тесты скриптов и MP-контрактов

```bash
# Скрипты benchmark
pytest tests/unit/scripts/test_prepare_multiprocessing_benchmark.py \
       tests/unit/scripts/test_render_multiprocessing_benchmark_report.py \
       tests/unit/scripts/test_benchmark_ipc_kpi_gate.py -q

# MP refactor unit tests
pytest tests/unit/core/test_mp_async_bridge.py \
       tests/unit/core/test_mp_pending_cap.py \
       tests/unit/core/test_sync_mp_adaptive.py \
       tests/unit/core/test_staleness_band.py \
       tests/unit/core/test_mp_queue_config.py \
       tests/unit/object_detector/test_detection_thread_yolo_mp_async.py \
       tests/unit/object_tracker/test_botsort_parent_init.py -q
```

Полный индекс MP-тестов: [tests/README.md](../tests/README.md).

---

## 12. Связанные документы

- [BENCHMARKS_MERGE_SCOPE.md](BENCHMARKS_MERGE_SCOPE.md) — рекомендации по merge ветки `benchmarks` в `main`
- [reports/mp_refactor_gate/gate_review_2026-06-13.md](../reports/mp_refactor_gate/gate_review_2026-06-13.md) — последняя проверка gate на HEAD
