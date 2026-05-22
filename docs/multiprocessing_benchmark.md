# Методика тестирования производительности мультипроцессного режима

Документ описывает воспроизводимый сценарий сравнения однопроцессного режима `thread` и мультипроцессного режима `process` для системы EvilEye. Цель тестов — показать, как мультипроцессное выполнение влияет на пропускную способность и стабильность обработки при росте числа камер.

## Базовый принцип

Для каждой точки измерения используется один и тот же набор видеоисточников, модель детектора, параметры FPS и параметры трекинга. Отличается только режим выполнения компонентов конвейера:

- `thread` — однопроцессный режим: захват, обнаружение и отслеживание работают в основном процессе с потоками.
- `process` — мультипроцессный режим: поддерживаемые стадии запускают дочерние процессы и обмениваются данными через IPC.

Зачётное сравнение проводится на Linux для 1, 2, 3 и 4 логических камер. В существующем базовом конфиге `configs/poly-videos-gst_gui_fixcheck_bench30.json` описано 5 логических камер: один обычный видеоисточник и два видеоисточника со split-разбиением на две области каждый, но для отчёта используются первые четыре точки нагрузки.

## Подготовка конфигов

Сгенерировать пары конфигов `thread`/`process`:

```bash
python scripts/prepare_multiprocessing_benchmark.py
```

По умолчанию скрипт использует Linux/GStreamer-конфиг `configs/poly-videos-gst_gui_fixcheck_bench30.json`, генерирует точки 1..4 камеры и сохраняет результат в `reports/bench_multiprocessing/configs/`.

Если видеофайлы из исходного конфига недоступны на текущей машине, скрипт завершится с понятным списком отсутствующих путей. Для подготовки шаблонов без проверки запуска можно использовать:

```bash
python scripts/prepare_multiprocessing_benchmark.py --allow-missing
```

Полезные параметры:

- `--base-config` — путь к исходному video-config.
- `--max-cameras` — максимальное число логических камер для генерации; для зачётного теста используется значение `4`.
- `--enable-server` — оставить web server включенным и переключать его `execution_mode` вместе с остальными стадиями.

## Запуск тестов

После подготовки конфигов выполнить headless-прогоны:

```bash
python scripts/run_multiprocessing_benchmark.py --camera-counts 1 2 3 4 --timeout-sec 180
```

Runner запускает `python -m evileye.process --no-gui --autoclose`, включает `EVILEYE_PERF_DIAG=1`, сохраняет логи в `reports/bench_multiprocessing/logs/` и системные сэмплы в `reports/bench_multiprocessing/samples/`.

Для частичного запуска отдельных точек:

```bash
python scripts/run_multiprocessing_benchmark.py --camera-counts 1 3 4 --modes thread process
```

Рекомендуется перед зачётными измерениями выполнить один прогревочный запуск, чтобы загрузка моделей и инициализация библиотек не искажали steady-state результаты.

## Формирование таблиц и графиков

После завершения прогонов:

```bash
python scripts/render_multiprocessing_benchmark_report.py
```

Скрипт создаёт:

- `reports/bench_multiprocessing/results.csv` — таблица с русскими заголовками для вставки в отчёт или электронную таблицу.
- `reports/bench_multiprocessing/report.md` — Markdown-отчёт с методикой, сводной таблицей и оценкой эффективности.
- `reports/bench_multiprocessing/plots/*.png` — графики сравнения режимов по числу камер.

## Метрики

Основные показатели:

- `Захват, кадры/с` — средний FPS источников по диагностическим строкам захвата.
- `Обнаружение, кадры/с` — оценка пропускной способности стадии detector по `PerfDiag(Pipeline)`.
- `Отслеживание, кадры/с` — оценка пропускной способности стадии tracker.
- `Визуализация, кадры/с` — оценка частоты обработки кадров для публикации/визуализации.
- `p95 цикла, мс` — 95-й перцентиль времени полного цикла конвейера.
- `CPU, %`, `RAM, ГБ`, `GPU-RAM, ГБ` — системные метрики, собранные runner-ом.
- `Ошибки`, `Traceback`, `Перезапуски` — признаки невалидного или нестабильного прогона.

GPU-RAM заполняется только при наличии `nvidia-smi`. Если GPU недоступен, поле останется пустым.

### Poly-videos (4 конфига) и MP barrier tuning

Сравнение `process` vs `thread` для [`configs/poly-videos.json`](../configs/poly-videos.json) и GST-аналогов:

```bash
python scripts/run_poly_videos_mode_compare.py --timeout-sec 180 --runs-per-config 5
python scripts/analyze_poly_mp_barriers.py
python scripts/measure_poly_e2e_fps.py --config configs/poly-videos.json --active-sec 120
python scripts/render_poly_videos_mode_report.py
```

**Сквозная метрика (primary):** `e2e_tracker_fps` из `measure_poly_e2e_fps.py` — уникальные пары `(source_id, frame_id)` на выходе `trackers` за активную фазу.  
**Controller loop Hz** (`pipeline_hz_est` в CSV) — частота вызова `pipeline.process()`, не равна E2E FPS в MP-режиме.

Переменные окружения (отдельные YOLO-процессы сохраняются):

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `EVILEYE_MP_QUEUE_SCALE` | `1` | Множитель размеров очередей detector/tracker/MpControl |
| `EVILEYE_MP_DRAIN_POLL_SEC` | `0.01` | Таймаут poll в feed/drain MP (сек) |
| `EVILEYE_PIPELINE_SYNC_MP` | `0` | Post-put sync drain в `processor_step` (bench/отладка) |
| `EVILEYE_PIPELINE_SYNC_MP_MS` | `8` | Макс. ожидание drain за тик (мс) |
| `EVILEYE_CONTROLLER_BACKPRESSURE` | `soft` | Доп. sleep в controller при росте MP pending (`0`/`off` — выкл.) |
| `EVILEYE_BACKPRESSURE_PENDING_THRESHOLD` | `8 × cameras` (soft) / `5 × cameras` (`1`) | Порог pending для доп. sleep |
| `EVILEYE_BACKPRESSURE_SLEEP_MS_PER_PENDING` | `1.5` (soft) / `2` (`1`) | мс sleep на единицу pending выше порога |
| `EVILEYE_BACKPRESSURE_SLEEP_MAX_MS` | `40` (soft) / `80` (`1`) | Потолок доп. sleep |
| `EVILEYE_MP_PENDING_CAP` | (auto) | Cap FIFO `MpAsyncBridge` pending (detector, drop oldest) |
| `EVILEYE_MP_PENDING_CAP_TRACKER` | `4` | Cap FIFO tracker pending |
| `EVILEYE_SKIP_PIPELINE_TICK_ON_BACKLOG` | `0` | Пропуск `pipeline.process()` при hard backlog (bench) |
| `EVILEYE_SKIP_PIPELINE_HARD_LIMIT` | `15 × cameras` | Порог pending для skip tick |
| `EVILEYE_PIPELINE_TIMELINE` | `0` | Детальный `PipelineTimeline(...)` в лог |

**Фаза 2 (backlog):** primary KPI — `mean_staleness_frames` (E2E), `mp_pending_max` (MpBarrier), `lag_ratio`; `pipeline_hz_est` — вторичный.  
`EVILEYE_MP_QUEUE_SCALE=1` по умолчанию; `SCALE=2` только если матрица показывает улучшение свежести без роста pending.

Матрица экспериментов:

```bash
./scripts/run_backlog_matrix.sh B1   # или all
python scripts/compare_poly_backlog_matrix.py --matrix-dir reports/poly_videos_mode_compare/experiments/backlog_matrix --write-winner
```

См. [`docs/mp_fps_phase2_summary.md`](mp_fps_phase2_summary.md) и [`docs/mp_fps_post_fix_summary.md`](mp_fps_post_fix_summary.md) (фаза 1, SCALE=2).

### Фаза 3 (E2E FPS, staleness band)

**Primary KPI:** `e2e_tracker_fps` (process) и `e2e_ratio` vs thread.  
**Ограничение:** `mean_staleness_frames ∈ [5.9, 6.5]` — не оптимизировать «свежесть» ниже 5.9.

| Переменная | По умолчанию / bench |
|------------|---------------------|
| `EVILEYE_PIPELINE_SYNC_MP` | `0` (bench: `adaptive`, не постоянный `1`) |
| `EVILEYE_SYNC_MP_PENDING_MAX` | `2 × cameras` (bench: `10`) |
| `EVILEYE_CONTROLLER_BACKPRESSURE` | **`soft`** (в коде) |
| `EVILEYE_MP_DRAIN_POLL_SEC` | **`0.01`** (в коде) |

```bash
./scripts/run_e2e_fps_matrix.sh all
python scripts/compare_poly_e2e_fps_matrix.py --matrix-dir reports/poly_videos_mode_compare/experiments/e2e_fps_matrix --write-winner
./scripts/run_phase3_winner_bench.sh
```

См. [`docs/mp_fps_phase3_summary.md`](mp_fps_phase3_summary.md) (выводы) и сырые артефакты в `reports/poly_videos_mode_compare/` (JSON/CSV). **Не дублируйте** полные таблицы матрицы в docs — только ссылка + интерпретация. Post-refactor gate: [`reports/mp_refactor_gate/`](../reports/mp_refactor_gate/).

## Интерпретация результата

Эффективность мультипроцессности считается по парным запускам с одинаковым числом камер:

```text
ускорение = FPS_process / FPS_thread
снижение задержки = (p95_thread - p95_process) / p95_thread
```

Ожидаемый эффект должен проявляться сильнее при увеличении числа камер: однопроцессный режим чаще упирается в общий цикл, очереди и конкуренцию потоков, а мультипроцессный режим позволяет изолировать тяжёлые стадии и лучше распределять работу между ядрами CPU. При этом вывод считается корректным только для прогонов без ошибок, tracebacks, таймаутов и неконтролируемых перезапусков воркеров.
