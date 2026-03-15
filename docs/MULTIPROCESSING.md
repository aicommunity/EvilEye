# Мультипроцессность в EvilEye

## Содержание

- [Запуск системы](#запуск-системы)
- [Обзор](#обзор)
- [Проблема GIL](#проблема-gil)
- [Архитектура решения](#архитектура-решения)
- [Компоненты, поддерживающие мультипроцессность](#компоненты-поддерживающие-мультипроцессность)
- [Конфигурация](#конфигурация)
- [Диаграммы последовательности](#диаграммы-последовательности)
- [Изменения архитектуры и новые сущности](#изменения-архитектуры-и-новые-сущности)
- [Жизненный цикл процессов](#жизненный-цикл-процессов)
- [Кросс-процессное логирование](#кросс-процессное-логирование)
- [Обратная совместимость](#обратная-совместимость)
- [Переменные окружения и единый стриминг (Config Run)](#переменные-окружения-и-единый-стриминг-config-run)
- [Каталог диаграмм](#каталог-диаграмм)
- [FAQ](#faq)

---

## Запуск системы

EvilEye предоставляет несколько способов запуска

### 1. Запуск пайплайна: `evileye run`

Основной способ запуска. Читает JSON-конфиг, инициализирует Controller,
поднимает пайплайн и (опционально) GUI

```bash
# С GUI (по умолчанию)
evileye run configs/single_video_multiprocess.json

# Без GUI (headless)
evileye run configs/single_video_multiprocess.json --no-gui

# С автозакрытием после окончания видео
evileye run configs/single_video_multiprocess.json --autoclose

# С подробным логированием
evileye run configs/single_video_multiprocess.json --verbose
```

### 2. Запуск веб-сервера: `evileye server`

Запускает FastAPI/Uvicorn как **основной процесс**. Пайплайны создаются
и управляются через REST API.

```bash
# Стандартный запуск
evileye server

# На конкретном хосте и порту
evileye server --host 0.0.0.0 --port 8000

# С автозапуском конфига после старта сервера
evileye server --config single_video_multiprocess.json

# С отключённым auto-reload
evileye server --no-reload

# С несколькими воркерами uvicorn
evileye server --workers 4
```

Параметры CLI:

| Флаг | Описание | По умолчанию |
|------|----------|-------------|
| `--host` | Адрес привязки | `127.0.0.1` |
| `--port` | Порт | `8080` |
| `--reload` / `--no-reload` | Авто-перезагрузка при изменении кода | `--reload` |
| `--workers` | Количество воркеров uvicorn | `1` |
| `--config` | Автозапуск конфига после старта | — |
| `--log-level` | Уровень логирования | `info` |
| `--verbose` | Подробные логи | `false` |

После запуска доступны:
- Swagger UI: `http://localhost:8080/docs`
- ReDoc: `http://localhost:8080/redoc`

**Важно**: при `evileye server` секция `"server"` из JSON-конфига **не читается**.
Все настройки сервера передаются через CLI-флаги. Секция `"server"` в конфиге
используется только при запуске через `evileye run` с `server.enabled: true`.

### 3. Прямой запуск: `evileye-process`

Запускает `process.py` напрямую, минуя CLI-обёртку и `scheduled_restart`.

```bash
evileye-process --config configs/single_video_multiprocess.json
evileye-process --config configs/single_video_multiprocess.json --no-gui
```

### 4. GUI-лаунчер: `evileye-launch`

Открывает графический интерфейс для выбора конфига и управления системой.

```bash
evileye-launch
evileye-launch configs/single_video_multiprocess.json
```

### Веб-сервер: два режима работы

Веб-сервер может работать в двух режимах:

**Режим A - Отдельный процесс (`evileye server`)**

```
┌──────────────────────────────────────┐
│  evileye server --port 8080          │
│  ┌────────────────────────────────┐  │
│  │  FastAPI / Uvicorn (основной)  │  │
│  │  REST API для управления       │  │
│  │  POST /configs/runs → запуск   │  │
│  │  GET /stream/{id} → видео      │  │
│  └────────────────────────────────┘  │
│  ┌────────────────────────────────┐  │
│  │  Config Run (дочерний процесс) │  │
│  │  Детекция, трекинг, атрибуты   │  │
│  │  Кадры → /tmp/evileye_frames/  │  │
│  └────────────────────────────────┘  │
└──────────────────────────────────────┘
```

Сервер - главный. Пайплайны запускаются как Config Runs через REST API
(`POST /api/v1/configs/runs`). Кадры из дочернего процесса попадают
в сервер через файловый IPC (_FramePoller читает `latest.jpg`).

**Режим B — Дочерний процесс (`evileye run` + `server.enabled: true`)**

```
┌──────────────────────────────────────┐
│  evileye run config.json             │
│  ┌────────────────────────────────┐  │
│  │  Controller (основной процесс) │  │
│  │  Pipeline, GUI, обработка      │  │
│  └──────────┬─────────────────────┘  │
│             │ mp.Queue (JPEG-кадры)  │
│  ┌──────────▼─────────────────────┐  │
│  │  FastAPI / Uvicorn (дочерний)  │  │
│  │  Только стриминг видео         │  │
│  │  GET /stream/{id}              │  │
│  └────────────────────────────────┘  │
└──────────────────────────────────────┘
```

Controller — главный. Сервер только транслирует кадры через `mp.Queue`.
Настройки берутся из секции `"server"` в JSON-конфиге.

### Пример: полный запуск с мультипроцессностью

```bash
# 1. Развернуть примеры (если ещё не сделано)
evileye deploy-samples

# 2. Посмотреть доступные конфиги
evileye list-configs

# 3. Запустить с мультипроцессным конфигом
evileye run configs/single_video_multiprocess.json

# 4. Проверить в логах, что процессы запустились:
#    - "Detection initialized in PROCESS mode with 1 worker(s)"
#    - "Started worker process pid=XXXX"
#    - "Process det-mp-0-worker ready"
```

### Пример: веб-сервер + мультипроцессность

```bash
# Вариант A: сервер отдельно, пайплайн через API
evileye server --host 0.0.0.0 --port 8080
# Затем через API: POST /api/v1/configs/runs для запуска пайплайна

# Вариант B: все в одном - сервер как дочерний процесс
# В конфиге: "server": {"enabled": true, "execution_mode": "process", "port": 8080}
evileye run configs/single_video_multiprocess.json
# Сервер автоматически поднимется на порту 8080
```

---

## Обзор

EvilEye поддерживает два режима выполнения для "тяжёлых" компонентов пайплайна:

| Режим | Параметр | Описание |
|-------|----------|----------|
| **Thread** | `"execution_mode": "thread"` | Потоки в одном процессе (по умолчанию) |
| **Process** | `"execution_mode": "process"` | Отдельные OS-процессы через `multiprocessing` |

Режим выбирается **для каждого компонента независимо** через JSON-конфигурацию.
Можно комбинировать: например, детекцию запустить в отдельном процессе,
а трекинг оставить в потоке

---

## Проблема GIL

Python имеет Global Interpreter Lock (GIL) - механизм, который не позволяет
нескольким потокам одновременно выполнять Python-байткод. При использовании
`multiprocessing` каждый процесс получает **свой GIL**, что обеспечивает
настоящий параллелизм:

![GIL: Threading vs Multiprocessing](images/mp_gil_comparison.png)

---

## Архитектура решения

### Общая схема

![Общая архитектура мультипроцессности](images/mp_architecture.png)

Общая архитектура системы с мультипроцессностью.
В центре — **основной процесс** (Main Process), содержащий Controller,
Pipeline, ProcessorStep/ProcessorFrame и GUI. От него отходят стрелки к
**дочерним процессам**: Detection Worker (YOLO-инференс), Tracking Worker, Attribute Workers (ROI Feeder + Classifier) и
Web Server (FastAPI/Uvicorn). Между основным и дочерними процессами
показаны `mp.Queue` для передачи данных и `mp.Queue` для логирования.
Каждый дочерний процесс обёрнут в `MpControl`, который управляет его
жизненным циклом. `ProcessManager` (синглтон) показан как реестр,
связывающий все `MpControl` экземпляры.

### Паттерн "Dispatcher Thread"

Каждый компонент в режиме `"process"` использует один и тот же паттерн:
dispatcher thread читает из внутренней `queue_in`, передаёт данные
в `mp.Queue` дочернего процесса, и забирает результаты обратно в `queue_out`.

Это позволяет остальному пайплайну (`ProcessorStep`, `ProcessorFrame` и т.д.)
работать **без изменений** — они по-прежнему вызывают `put()` и `get()`
на компоненте, не зная, работает ли он в потоке или процессе.

![Паттерн Dispatcher Thread](images/mp_dispatcher_pattern.png)

**Что изображено на схеме**: три колонки - Pipeline (ProcessorStep),
Dispatcher Thread, Child Process. Показан путь данных:
1. ProcessorStep вызывает `component.put(data)` — данные попадают в `queue_in`
2. Dispatcher Thread читает из `queue_in`, вызывает `mp_control.put(data)` —
   данные сериализуются через pickle и попадают в `mp.Queue` (input)
3. Child Process (MpWorker) читает из `mp.Queue`, вызывает `worker_impl(data)`,
   кладёт результат в `mp.Queue` (output)
4. Dispatcher Thread читает результат из `mp_control.get()`, кладёт в `queue_out`
5. ProcessorStep вызывает `component.get()` — получает результат

ProcessorStep не знает, работает ли компонент в потоке
или процессе — интерфейс `put()`/`get()` одинаков в обоих режимах.

---

## Компоненты, поддерживающие мультипроцессность

| Компонент | Класс | Файл воркера | Что выносится в процесс |
|-----------|-------|-------------|------------------------|
| **Детекция** | `ObjectDetectorYolo` | `mp_worker_yolo.py` | YOLO/RT-DETR инференс (GPU) |
| **Трекинг** | `ObjectTrackingBotsort` | `mp_worker_tracker.py` | BOTSORT + ONNX-энкодер (CPU) |
| **ROI Feeder** | `RoiFeeder` | `mp_worker_attributes.py` | ROI |
| **Атрибуты** | `AttributeClassifier` | `mp_worker_attributes.py` | YOLO |
| **Веб-сервер** | `ServerProcessManager` | `server.py` | FastAPI + Uvicorn |

---

## Конфигурация

### Принцип

Параметр `"execution_mode"` добавляется в секцию конкретного компонента.
Допустимые значения:

- `"thread"` - потоковый режим (по умолчанию, если параметр не указан)
- `"process"` - мультипроцессный режим

### Примеры

#### Только детекция в отдельном процессе

```json
{
    "pipeline": {
        "detectors": [
            {
                "model": "models/yolo11n.pt",
                "source_ids": [0],
                "execution_mode": "process"
            }
        ],
        "trackers": [
            {
                "source_ids": [0]
            }
        ]
    }
}
```

> Трекинг остаётся в потоке (execution_mode не указан → "thread")

#### Детекция + трекинг в процессах

```json
{
    "pipeline": {
        "detectors": [
            {
                "model": "models/yolo11n.pt",
                "source_ids": [0],
                "execution_mode": "process"
            }
        ],
        "trackers": [
            {
                "source_ids": [0],
                "execution_mode": "process"
            }
        ]
    }
}
```

#### Полная мультипроцессность + веб-сервер

```json
{
    "pipeline": {
        "detectors": [
            {
                "model": "models/yolo11n.pt",
                "source_ids": [0],
                "execution_mode": "process"
            }
        ],
        "trackers": [
            {
                "source_ids": [0],
                "execution_mode": "process"
            }
        ],
        "attributes_roi": [
            {
                "source_ids": [0],
                "execution_mode": "process"
            }
        ],
        "attributes_classifier": [
            {
                "model": "models/attr_model.pt",
                "source_ids": [0],
                "execution_mode": "process"
            }
        ]
    },
    "server": {
        "enabled": true,
        "execution_mode": "process",
        "host": "0.0.0.0",
        "port": 8080
    }
}
```

#### Всё в потоках (по умолчанию, обратная совместимость)

```json
{
    "pipeline": {
        "detectors": [
            {
                "model": "models/yolo11n.pt",
                "source_ids": [0]
            }
        ],
        "trackers": [
            {
                "source_ids": [0]
            }
        ]
    }
}
```

---

## Диаграммы последовательности

В этом разделе представлены 6 sequence-диаграмм, каждая из которых
показывает взаимодействие компонентов во времени (сверху вниз) для
конкретного сценария.

### 1. Инициализация компонента в режиме "process"

![Sequence: инициализация в process mode](images/mp_seq_init.png)

пошаговый процесс инициализации компонента (на примере
детектора) при `execution_mode: "process"`.

Участники: **Controller**, **ObjectDetectorYolo**, **MpControl**, **MpWorkerYolo** (child process).

Последовательность:
1. Controller вызывает `detector.set_params(params)` — детектор читает
   `execution_mode` из конфига, пересоздаёт очереди как `mp.Queue`
2. Controller вызывает `detector.init()` — детектор вызывает `_init_process_mode()`
3. Создаётся `MpControl(name="det-mp-0")` с `input_queue` и `output_queue`
4. `MpControl.add_worker(MpWorkerYolo)` — создаётся экземпляр воркера,
   ему передаются общие очереди и `log_queue`
5. `worker.set_params(model_name, classes, inf_params)` — параметры
   сохраняются в воркере (модель ещё не загружена)
6. `MpControl.start()` — создаётся `mp.Process(target=worker, daemon=True)`,
   процесс запускается
7. Внутри дочернего процесса: `worker.__call__()` → `_init_logger()` →
   `init_worker()` (загрузка YOLO-модели) → основной цикл
8. Запускается health monitor thread и log listener thread

### 2. Обработка кадра (детекция в процессе)

![Sequence: обработка кадра](images/mp_seq_frame_processing.png)

путь одного видеокадра через систему детекции
в процессном режиме

Участники: **Source** (видеозахват), **ProcessorStep**, **ObjectDetectorYolo**,
**Dispatcher Thread**, **MpControl**, **MpWorkerYolo** (child process).

Последовательность:
1. Source выдаёт `CaptureImage` (кадр + метаданные)
2. ProcessorStep вызывает `detector.put(image)` — кадр попадает в `queue_in`
3. Dispatcher Thread (работает в основном процессе) читает из `queue_in`
4. Dispatcher передаёт кадр в `mp_control.put()` → данные сериализуются
   через pickle → попадают в `mp.Queue` (input)
5. MpWorkerYolo в дочернем процессе: `input_queue.get()` → `worker_impl(data)` →
   `model.predict()` → результаты переносятся на CPU (`result.cpu()`)
6. Результаты кладутся в `mp.Queue` (output) → десериализация в основном процессе
7. Dispatcher читает результат из `mp_control.get()`, кладёт в `queue_out`
8. ProcessorStep вызывает `detector.get()` → получает `DetectionResultList`

### 3. Полный пайплайн с мультипроцессностью

![Sequence: полный пайплайн](images/mp_seq_full_pipeline.png)

**Что изображено**: полный путь кадра через все этапы пайплайна, когда
детекция, трекинг и атрибуты работают в отдельных процессах.

Участники: **Source**, **Detector** (process), **Tracker** (process),
**RoiFeeder** (process), **AttributeClassifier** (process),
**Controller**, **Visualizer**.

Последовательность:
1. Source → Detector: `CaptureImage` → `DetectionResultList`
2. Detector → Tracker: `(DetectionResultList, CaptureImage)` → `(TrackingResultList, CaptureImage)`
3. Tracker → RoiFeeder: добавляет `roi_data` (вырезанные кропы) к `TrackingResultList`
4. RoiFeeder → AttributeClassifier: классифицирует кропы, добавляет `attr_results`
5. Результат возвращается в Controller → ObjectsHandler → Visualizer → GUI

Между каждым этапом данные проходят через `mp.Queue` (pickle-сериализация).
Каждый этап работает в своём процессе и не блокирует остальные.

### 4. Graceful shutdown

![Sequence: graceful shutdown](images/mp_seq_shutdown.png)

процедура корректной остановки системы при вызове
`Controller.stop()`.

Участники: **Controller**, **MpControl** (для каждого компонента),
**MpWorker** (дочерние процессы), **Health Monitor**, **Log Listener**.

Последовательность:
1. Controller вызывает `detector.stop()` → `mp_control.stop(timeout=5.0)`
2. `_monitor_stop.set()` — останавливает health monitor thread
3. Для каждого воркера: `input_queue.put(None)` — poison pill
4. Для каждого воркера: `worker._stop_event.set()` — дополнительный сигнал
5. Дочерний процесс: `input_queue.get()` возвращает `None` → выход из цикла →
   `cleanup()` (освобождение GPU) → процесс завершается
6. `process.join(timeout)` — ожидание завершения
7. Если процесс не завершился: `process.terminate()` → `join(1.0)` → `process.kill()`
8. `_log_queue.put(None)` — останавливает log listener
9. Аналогично для трекера, атрибутов и сервера

### 5. Автоматический перезапуск упавшего воркера

![Sequence: автоперезапуск](images/mp_seq_auto_restart.png)

сценарий, когда дочерний процесс аварийно завершается
(segfault, OOM, необработанное исключение) и health monitor автоматически
его перезапускает.

Участники: **MpWorkerYolo** (child process), **Health Monitor** (thread в основном процессе),
**MpControl**, **New MpWorkerYolo** (новый child process).

Последовательность:
1. MpWorkerYolo аварийно завершается (exitcode != 0)
2. Health Monitor (проверяет `is_alive()` каждые 2 секунды) обнаруживает,
   что процесс мёртв
3. Логирует: `"Worker pid=XXXX exited with code Y, restarting"`
4. Создаёт новый `mp.Process(target=workers_list[i], daemon=True)`
5. Запускает новый процесс: `new_p.start()`
6. Заменяет ссылку в `processes[i]` на новый процесс
7. Логирует: `"Restarted worker as pid=ZZZZ"`
8. Новый воркер проходит полный цикл инициализации: `_init_logger()` →
   `init_worker()` (загрузка модели) → основной цикл
9. Система продолжает работу без вмешательства оператора

### 6. Веб-сервер в отдельном процессе (IPC через mp.Queue)

![Sequence: веб-сервер IPC](images/mp_seq_web_server.png)

механизм передачи JPEG-кадров из основного процесса
(Controller) в дочерний процесс (FastAPI/Uvicorn) через `mp.Queue`.

Участники: **Controller** (основной процесс), **ServerProcessManager**,
**mp.Queue** (frame_queue), **FrameBroker** (в дочернем процессе),
**IPC Listener Thread**, **FastAPI** (HTTP endpoint `/stream/{id}`),
**Browser** (клиент).

Последовательность:
1. Controller кодирует кадр в JPEG: `cv2.imencode('.jpg', frame)`
2. Вызывает `server_process_manager.publish_frame(pipeline_id, jpeg_bytes)`
3. ServerProcessManager кладёт `(pipeline_id, jpeg_bytes)` в `mp.Queue(maxsize=30)`.
   Если очередь полна — удаляет самый старый кадр (drop oldest)
4. В дочернем процессе: IPC Listener Thread (`_ipc_listener_loop`)
   читает из `mp.Queue`
5. Вызывает `broker.publish_jpeg(pipeline_id, jpeg_bytes)` — кадр
   сохраняется в `FrameBroker._frames`
6. Когда браузер запрашивает `GET /stream/{pipeline_id}`:
   FastAPI endpoint вызывает `broker.latest_jpeg(pipeline_id)`
   и отдаёт кадр как часть MJPEG-потока

---

## Изменения архитектуры и новые сущности

Ниже описаны **все** новые классы, файлы и изменения в существующих классах,
введённые для поддержки мультипроцессности. Для каждой сущности указано:
зачем она нужна, какую проблему решает, как связана с остальными

---

### Обзор изменений

**Новые файлы**

| Файл | Что содержит |
|------|-------------|
| `evileye/core/mp_worker.py` | Абстрактный базовый класс `MpWorker` |
| `evileye/core/mp_control.py` | Контроллер пула процессов `MpControl` |
| `evileye/core/process_manager.py` | Синглтон-реестр `ProcessManager` |
| `evileye/object_tracker/mp_worker_tracker.py` | Воркер трекинга `MpWorkerTracker` |
| `evileye/attributes_detection/mp_worker_attributes.py` | Воркеры атрибутов `MpWorkerRoiFeeder`, `MpWorkerAttributeClassifier` |
| `configs/single_video_multiprocess.json` | Пример конфига с `execution_mode: "process"` |



### 1. MpWorker — базовый класс воркера

> См. также: [Жизненный цикл процессов](#жизненный-цикл-процессов) (диаграмма состояний),
> [Кросс-процессное логирование](#кросс-процессное-логирование) (схема пересылки логов)

**Файл**: `evileye/core/mp_worker.py` 

**Зачем**: определяет единый контракт для всех компонентов, работающих
в дочерних процессах. Без этого класса каждый компонент (детекция, трекинг,
атрибуты) реализовывал бы свой цикл жизни, обработку ошибок и логирование
по-разному

ML-модели нельзя передать через pickle между
процессами (GPU-тензоры, ONNX-сессии). `MpWorker` гарантирует, что модель
загружается **внутри** дочернего процесса через `init_worker()`, а не в
родительском

**Иерархия наследования**:

```
MpWorker (ABC)
├── MpWorkerYolo           — YOLO-детекция
├── MpWorkerTracker        — BoTSORT-трекинг + ONNX ReID
├── MpWorkerRoiFeeder      — вырезка ROI-кропов
└── MpWorkerAttributeClassifier — классификация атрибутов
```

**Жизненный цикл** (метод `__call__`, вызывается как target для `mp.Process`):

```
__call__()
  │
  ├── _init_logger()          # QueueHandler → пересылка логов в родительский процесс
  │
  ├── init_worker()           # Загрузка YOLO/ONNX/BoTSORT (абстрактный, реализуется наследником)
  │
  ├── while not _stop_event:  # Основной цикл
  │     ├── data = input_queue.get(timeout=2)
  │     ├── if data is None: break   # Poison pill → выход
  │     ├── result = worker_impl(data)  # Обработка (абстрактный)
  │     └── output_queue.put(result)
  │
  └── cleanup()               # Освобождение GPU-памяти, закрытие сессий
```

**Ключевые атрибуты**:

| Атрибут | Тип | Назначение |
|---------|-----|-----------|
| `input_queue` | `mp.Queue` | Входные данные от родителя |
| `output_queue` | `mp.Queue` | Результаты обратно в родителя |
| `log_queue` | `mp.Queue` | Пересылка `LogRecord` в родительский процесс |
| `_stop_event` | `mp.Event` | Сигнал остановки без poison pill |
| `logger` | `logging.Logger` | Логгер дочернего процесса |

**Абстрактные методы** (обязательны для наследников):

| Метод | Что делает |
|-------|-----------|
| `init_worker()` | Загрузка модели/ресурсов внутри дочернего процесса |
| `worker_impl(data)` | Обработка одного элемента данных, возврат результата |

**Переопределяемые методы** (опциональны):

| Метод | Что делает |
|-------|-----------|
| `cleanup()` | Освобождение ресурсов перед выходом из процесса |

---

### 2. MpControl — контроллер пула процессов

> См. также: [Graceful shutdown](#4-graceful-shutdown) (диаграмма остановки),
> [Автоперезапуск](#5-автоматический-перезапуск-упавшего-воркера) (диаграмма рестарта),
> [Инициализация компонента](#1-инициализация-компонента-в-режиме-process) (диаграмма запуска)

**Файл**: `evileye/core/mp_control.py`

**Зачем**: управляет одним или несколькими `MpWorker`-процессами как единым
пулом. Предоставляет родительскому процессу простой интерфейс `put()`/`get()`
для отправки данных и получения результатов, скрывая всю сложность управления
процессами.

**Проблемы, которые решает**:
- **Запуск**: создание `mp.Process` с правильными аргументами, daemon-режим
- **Мониторинг**: фоновый поток проверяет `is_alive()` каждые 2 секунды
- **Автоперезапуск**: если воркер упал (segfault, OOM, исключение) — автоматически
  создаётся новый процесс с тем же воркером
- **Graceful shutdown**: 3-уровневая остановка (poison pill → terminate → kill)
- **Кросс-процессное логирование**: `_log_queue` + listener thread

**Архитектура внутри MpControl**:

```
MpControl
├── input_queue   (mp.Queue)  ← put() от родителя
├── output_queue  (mp.Queue)  → get() к родителю
├── _log_queue    (mp.Queue)  ← LogRecord от дочерних процессов
│
├── workers_list  [MpWorker, ...]   — зарегистрированные воркеры
├── processes     [mp.Process, ...]  — запущенные процессы
│
├── _log_listener      (threading.Thread)  — читает _log_queue, пишет в logging
└── _monitor_thread    (threading.Thread)  — health check + auto-restart
```

**Основные методы**:

| Метод | Что делает |
|-------|-----------|
| `add_worker(cls, *args, **kwargs)` | Создаёт экземпляр воркера, передаёт ему общие очереди и `log_queue` |
| `start()` | Запускает все воркеры как `mp.Process(daemon=True)`, стартует log listener и health monitor |
| `stop(timeout=5.0)` | Отправляет poison pill каждому воркеру, ждёт `timeout`, затем `terminate()`/`kill()` |
| `put(data)` / `get()` | Прокси к `input_queue.put()` / `output_queue.get()` |
| `is_alive()` | Есть ли хотя бы один живой процесс |
| `worker_count()` | Количество живых процессов |

**Процедура остановки** (`stop()`):

```
1. _monitor_stop.set()           — остановить health monitor
2. input_queue.put(None) × N     — poison pill для каждого воркера
3. worker._stop_event.set() × N  — дополнительный сигнал остановки
4. process.join(timeout) × N     — ожидание завершения
5. process.terminate() → join(1) — принудительное завершение
6. process.kill()                — крайняя мера (SIGKILL)
7. _log_queue.put(None)          — остановить log listener
```

---

### 3. ProcessManager — централизованный реестр пулов

**Файл**: `evileye/core/process_manager.py`

**Зачем**: когда в системе работают несколько `MpControl` (детекция, трекинг,
атрибуты, сервер), нужна единая точка для их управления. `ProcessManager` —
это синглтон, который позволяет остановить все пулы одной командой или
получить статус всех процессов.

**Паттерн**: Module-level Singleton через `get_process_manager()` с
double-checked locking (`threading.Lock`).

**Методы**:

| Метод | Что делает |
|-------|-----------|
| `register(name, pool)` | Добавить `MpControl` в реестр под именем |
| `unregister(name)` | Убрать из реестра, вернуть `MpControl` |
| `get(name)` | Получить `MpControl` по имени |
| `start_all()` | Вызвать `start()` на всех зарегистрированных пулах |
| `stop_all(timeout)` | Вызвать `stop()` на всех пулах |
| `status()` | `{name: {"alive": bool, "workers": int}}` для каждого пула |
| `shutdown()` | `stop_all()` + очистка реестра |

**Пример использования**:

```python
from evileye.core import get_process_manager

pm = get_process_manager()
pm.register("detection", det_mp_control)
pm.register("tracking", track_mp_control)

print(pm.status())
# {"detection": {"alive": True, "workers": 1},
#  "tracking": {"alive": True, "workers": 1}}

pm.shutdown()
```

---

### 4. MpWorkerYolo — воркер YOLO-детекции

**Файл**: `evileye/object_detector/mp_worker_yolo.py` (изменён)

**Зачем**: выполняет YOLO-инференс в дочернем процессе, освобождая
основной процесс от GPU-нагрузки.

**Что было**: класс существовал, но не поддерживал `log_queue`,
`_stop_event` и `cleanup()`.

**Что изменилось**:
- `__init__` принимает `log_queue` и передаёт его в `MpWorker`
- `cleanup()` удаляет YOLO-модель и освобождает GPU-память
- Наследуется от обновлённого `MpWorker` с поддержкой graceful shutdown

**Поток данных**:

```
input_queue.get() → list[CaptureImage]
    │
    ▼
model.predict(images, classes=..., verbose=False)
    │
    ▼
[result.cpu() for result in results]  → output_queue.put()
```

---

### 5. MpWorkerTracker — воркер BoTSORT-трекинга

> См. также: [Полный пайплайн](#3-полный-пайплайн-с-мультипроцессностью) (диаграмма — трекинг как второй этап)

**Файл**: `evileye/object_tracker/mp_worker_tracker.py` (новый)

**Зачем**: трекинг с ReID (re-identification) использует ONNX-энкодер,
который загружает нейросеть. В потоковом режиме это блокирует GIL.
Вынос в отдельный процесс позволяет трекингу работать параллельно
с детекцией.

**Проблема сериализации**: `BOTSORT` и `OnnxEncoder` нельзя передать
через pickle. Поэтому `init_worker()` создаёт `BotSortCfg` dataclass,
инициализирует `BOTSORT` и `OnnxEncoder` **внутри** дочернего процесса.

**Поток данных**:

```
input_queue.get() → (DetectionResultList, CaptureImage)
    │
    ├── Извлечь bboxes, confidences, class_ids
    ├── Создать Boxes объект (ultralytics)
    ├── tracker.update(boxes, image)
    ├── Сформировать TrackingResultList
    │
    ▼
output_queue.put() → (TrackingResultList, CaptureImage)
```

---

### 6. MpWorkerRoiFeeder — воркер вырезки ROI

**Файл**: `evileye/attributes_detection/mp_worker_attributes.py` (новый)

**Зачем**: вырезка ROI-кропов из кадра по bounding box'ам трекера.
Операция CPU-bound (numpy slicing), при большом количестве объектов
может стать bottleneck.

**Поток данных**:

```
input_queue.get() → (TrackingResultList, CaptureImage)
    │
    ├── Для каждого track: вырезать roi_image из frame
    ├── Добавить roi_data к tracking_data
    │
    ▼
output_queue.put() → (TrackingResultList + roi_data, CaptureImage)
```

---

### 7. MpWorkerAttributeClassifier — воркер классификации атрибутов

**Файл**: `evileye/attributes_detection/mp_worker_attributes.py` (новый)

**Зачем**: запускает YOLO-модель для классификации атрибутов (каска,
рюкзак, жилет и т.д.) на ROI-кропах. Это второй GPU-инференс в
пайплайне (после основной детекции), и его вынос в отдельный процесс
позволяет использовать GPU параллельно.

**Поток данных**:

```
input_queue.get() → (TrackingResultList + roi_data, CaptureImage)
    │
    ├── Для каждого roi_info в roi_data:
    │     ├── yolo_model.predict(roi_image)
    │     └── Сформировать attr_results[track_id]
    ├── Добавить attr_results к tracking_data
    │
    ▼
output_queue.put() → (TrackingResultList + attr_results, CaptureImage)
```

---

### 8. ServerProcessManager — веб-сервер в отдельном процессе

> См. также: [Веб-сервер IPC](#6-веб-сервер-в-отдельном-процессе-ipc-через-mpqueue) (sequence-диаграмма)

**Файл**: `evileye/server.py` 

**Зачем**: FastAPI/Uvicorn обрабатывает HTTP-запросы и MJPEG-стриминг.
В однопроцессном режиме сетевые операции конкурируют с пайплайном за GIL.
Вынос в отдельный процесс изолирует веб-сервер от вычислительной нагрузки.

**Новые сущности в файле**:

| Сущность | Тип | Назначение |
|----------|-----|-----------|
| `ServerProcessManager` | Класс | Управление жизненным циклом серверного процесса |
| `_run_server_in_process()` | Функция | Entry point для дочернего процесса (target для `mp.Process`) |

**Как работает IPC**:

```
Основной процесс                  Дочерний процесс (сервер)
┌─────────────────┐                ┌─────────────────────────┐
│  Controller.run  │                │  _run_server_in_process  │
│                  │                │                          │
│  jpeg = encode() │                │  broker = get_broker()   │
│       │          │                │  broker.set_ipc_queue(q) │
│       ▼          │                │       │                  │
│  spm.publish_    │   mp.Queue     │       ▼                  │
│  frame(id, jpeg)─┼───────────────►│  _ipc_listener_loop()    │
│                  │  (pipeline_id, │  broker.publish_jpeg()   │
│                  │   jpeg_bytes)  │       │                  │
│                  │                │       ▼                  │
│                  │                │  GET /stream/{id}        │
│                  │                │  → MJPEG response        │
└─────────────────┘                └─────────────────────────┘
```

**Методы ServerProcessManager**:

| Метод | Что делает |
|-------|-----------|
| `start(host, port, log_level)` | Создаёт `mp.Queue(maxsize=30)`, запускает `mp.Process` |
| `publish_frame(pipeline_id, jpeg)` | Кладёт `(pipeline_id, jpeg_bytes)` в очередь; при переполнении — drop oldest |
| `stop(timeout)` | Poison pill → join → terminate → kill |
| `is_alive()` | Проверка состояния процесса |

---

### 9. Изменения в FrameBroker — IPC-мост для кадров

**Файл**: `evileye/api/core/frame_broker.py` (изменён)

**Зачем**: `FrameBroker` хранит последний JPEG-кадр для каждого пайплайна
и отдаёт его по запросу `/stream/{id}`. Когда сервер работает в отдельном
процессе, кадры приходят не через прямой вызов `publish_jpeg()`, а через
`mp.Queue`.

**Новые атрибуты**:

| Атрибут | Тип | Назначение |
|---------|-----|-----------|
| `_ipc_queue` | `mp.Queue \| None` | Очередь для приёма кадров из основного процесса |
| `_ipc_thread` | `threading.Thread \| None` | Фоновый поток, читающий из `_ipc_queue` |
| `_ipc_stop` | `threading.Event` | Сигнал остановки IPC-потока |

**Новые методы**:

| Метод | Что делает |
|-------|-----------|
| `set_ipc_queue(queue)` | Подключает `mp.Queue`, запускает `_ipc_listener_loop` |
| `_ipc_listener_loop()` | Бесконечный цикл: `queue.get()` → `publish_jpeg()` |
| `stop_ipc()` | Останавливает IPC-поток |

---

### 10. Изменения в ObjectDetectorBase — базовый класс детекторов

**Файл**: `evileye/object_detector/object_detection_base.py` (изменён)

**Зачем**: все детекторы (YOLO, RT-DETR, RF-DETR) наследуются от этого
класса. Добавление `execution_mode` здесь позволяет **любому** детектору
работать в процессном режиме без дублирования кода.

**Новые атрибуты**:

| Атрибут | Тип | Назначение |
|---------|-----|-----------|
| `execution_mode` | `str` | `"thread"` или `"process"` |
| `_mp_control` | `MpControl \| None` | Пул процессов (если `execution_mode == "process"`) |

**Изменённые методы**:

| Метод | Что изменилось |
|-------|---------------|
| `__init__()` | Добавлен `execution_mode`, `_mp_control` |
| `_init_queues()` | Создаёт `mp.Queue` или `queue.Queue` в зависимости от `execution_mode` |
| `set_params_impl()` | Читает `execution_mode` из конфига, пересоздаёт очереди при смене режима |
| `get_params_impl()` | Возвращает `execution_mode` |
| `stop()` | Останавливает `_mp_control` если активен |
| `release_impl()` | Останавливает `_mp_control` |

**Почему очереди пересоздаются**: `queue.Queue` (threading) и `mp.Queue`
(multiprocessing) — разные классы. `mp.Queue` использует pipe + pickle
для передачи данных между процессами, а `queue.Queue` — просто `deque`
с `Lock`. Нельзя передать `queue.Queue` в дочерний процесс.

---

### 11. Изменения в ObjectDetectorYolo — YOLO-детектор

**Файл**: `evileye/object_detector/object_detection_yolo.py` (изменён)

**Зачем**: конкретная реализация детектора. Здесь происходит ветвление
на потоковый и процессный режимы.

**Новые методы**:

| Метод | Что делает |
|-------|-----------|
| `_init_thread_mode(inf_params)` | Создаёт `DetectionThreadYolo` (старое поведение) |
| `_init_process_mode(inf_params)` | Создаёт `DetectionThreadYoloMp` (через `MpControl`) |

**Изменённый `init_impl()`**:

```python
def init_impl(self):
    super().init_impl()
    inf_params = { ... }

    if self.execution_mode == EXEC_MODE_PROCESS:
        return self._init_process_mode(inf_params)
    return self._init_thread_mode(inf_params)
```

---

### 12. Изменения в DetectionThreadYoloMp — обёртка для процессного детектора

**Файл**: `evileye/object_detector/detection_thread_yolo_mp.py` (изменён)

**Зачем**: этот класс существовал до рефакторинга как экспериментальный
мультипроцессный детектор. Теперь он обновлён для работы с новым `MpControl`
API и используется как стандартный механизм процессной детекции.

**Что изменилось**:
- `__init__` создаёт `MpControl` с уникальным именем (`det-mp-0`, `det-mp-1`, ...)
- `MpWorkerYolo` получает `log_queue` через `MpControl.add_worker()`
- Добавлен `stop()` для остановки `MpControl`
- Интерфейс `predict()` / `get_bboxes()` не изменился — остальной пайплайн
  не знает, что внутри работает отдельный процесс

---

### 13. Изменения в ObjectTrackingBase — базовый класс трекеров

> См. также: [Паттерн Dispatcher Thread](#паттерн-dispatcher-thread) (схема паттерна)

**Файл**: `evileye/object_tracker/object_tracking_base.py` (изменён)

**Зачем**: аналогично `ObjectDetectorBase`, добавляет поддержку
`execution_mode` для всех трекеров.

**Новые атрибуты и методы**:

| Сущность | Тип | Назначение |
|----------|-----|-----------|
| `execution_mode` | `str` | `"thread"` или `"process"` |
| `_mp_control` | `MpControl \| None` | Пул процессов |
| `_init_process_mode()` | Метод | Создаёт `MpControl` + `MpWorkerTracker` + dispatcher thread |
| `_process_dispatch_loop()` | Метод | Dispatcher: `queue_in` → `mp_control.put()` → `mp_control.get()` → `queue_out` |

**Паттерн Dispatcher Thread**:

Dispatcher thread — ключевой архитектурный паттерн. Это обычный
`threading.Thread` в основном процессе, который:

1. Читает данные из `queue_in` (куда пишет предыдущий шаг пайплайна)
2. Передаёт их в `mp_control.put()` (→ `mp.Queue` → дочерний процесс)
3. Ждёт результат из `mp_control.get()` (← `mp.Queue` ← дочерний процесс)
4. Кладёт результат в `queue_out` (откуда читает следующий шаг пайплайна)

Этот паттерн **изолирует** мультипроцессность от остального пайплайна.
`ProcessorStep` и `ProcessorFrame` по-прежнему вызывают `put()`/`get()`
на компоненте и не знают, работает ли он в потоке или процессе.

```
ProcessorStep                    Dispatcher Thread              Child Process
     │                                │                              │
     │  component.put(data)           │                              │
     ├───────────────────────────────►│                              │
     │                                │  mp_control.put(data)        │
     │                                ├─────────────────────────────►│
     │                                │                              │ worker_impl(data)
     │                                │         mp_control.get()     │
     │                                │◄─────────────────────────────┤
     │  component.get() → result      │                              │
     │◄───────────────────────────────┤                              │
```

---

### 14. Изменения в RoiFeeder — процессор вырезки ROI

**Файл**: `evileye/attributes_detection/roi_feeder.py` (изменён)

**Что изменилось**:
- Добавлен `execution_mode` в `__init__`, `set_params_impl`, `get_params_impl`
- `init_impl()` вызывает `_init_process_mode()` при `execution_mode == "process"`
- `_init_process_mode()` создаёт `MpControl` + `MpWorkerRoiFeeder` + dispatcher thread
- `stop()` и `release_impl()` останавливают `_mp_control`

---

### 15. Изменения в AttributeClassifier — классификатор атрибутов

**Файл**: `evileye/attributes_detection/attribute_classifier.py` (изменён)

**Что изменилось**:
- Добавлен `execution_mode` в `__init__`, `set_params_impl`, `get_params_impl`
- `init_impl()` ветвится на `_init_thread_mode()` и `_init_process_mode()`
- В потоковом режиме: YOLO-модель загружается в основном процессе
- В процессном режиме: `MpControl` + `MpWorkerAttributeClassifier` + dispatcher thread
- `model_path` и `attrs` инициализированы в `__init__` (ранее определялись только в `set_params_impl`)

---

### 16. Изменения в Controller — центральный оркестратор

**Файл**: `evileye/controller/controller.py` (изменен)

**Что изменилось**:

| Место | Изменение |
|-------|----------|
| `__init__()` | Добавлен `self._server_process_manager = None`. Добавлена инициализация `_frame_dir` из env `EVILEYE_FRAME_DIR` для файлового IPC |
| `init()` | Проверяет `server.execution_mode == "process"` и `server.enabled == True`; если оба, создает `ServerProcessManager` и вызывает `start()` |
| `_publish_frame()` | Если `_frame_dir` задан, записывает JPEG в `latest.jpg` (atomic rename через `.latest.tmp` + `Path.replace`). Иначе публикует в локальный FrameBroker / `ServerProcessManager` |
| `run()` | После кодирования JPEG вызывает `self._publish_frame(jpeg_bytes)` |
| `stop()` | Вызывает `_server_process_manager.stop()` перед остановкой пайплайна |

---

### 17. Изменения в ProcessorBase — базовый класс процессоров пайплайна

**Файл**: `evileye/core/processor_base.py` (изменён)

**Что изменилось**:
- Добавлен атрибут `execution_mode` в `__init__`
- `set_params()` читает `execution_mode` из первого блока параметров
  и сохраняет его — это позволяет оркестратору знать, в каком режиме
  работает компонент

---

### 18. Изменения в core/__init__.py — экспорт новых классов

**Файл**: `evileye/core/__init__.py` (изменён)

**Добавлены импорты**:

```python
from .mp_worker import MpWorker
from .mp_control import MpControl
from .process_manager import ProcessManager, get_process_manager
```

Это позволяет другим модулям импортировать инфраструктурные классы через
`from evileye.core import MpWorker, MpControl, get_process_manager`.

---

### Сводная диаграмма зависимостей

```
                    ┌─────────────────┐
                    │  ProcessManager  │  (синглтон-реестр)
                    │  (process_      │
                    │   manager.py)   │
                    └────────┬────────┘
                             │ register/stop_all
                    ┌────────▼────────┐
                    │    MpControl    │  (контроллер пула)
                    │  (mp_control.py)│
                    └──┬──────────┬───┘
                       │          │
              add_worker()    start()/stop()
                       │          │
              ┌────────▼──┐  ┌────▼──────────┐
              │  MpWorker  │  │  mp.Process   │
              │  (ABC)     │  │  (daemon)     │
              └─────┬──────┘  └───────────────┘
                    │
        ┌───────────┼───────────┬──────────────┐
        │           │           │              │
   MpWorkerYolo  MpWorker   MpWorkerRoi    MpWorkerAttr
   (детекция)    Tracker    Feeder         Classifier
                 (трекинг)  (ROI)          (атрибуты)


  Компоненты пайплайна:

  ObjectDetectorBase ──► ObjectDetectorYolo ──► DetectionThreadYoloMp
        │                                              │
        │ execution_mode                               │ mp_control
        │                                              │
  ObjectTrackingBase ──► ObjectTrackingBotsort          │
        │                                              │
        │ _process_dispatch_loop()                     │
        │                                              │
  RoiFeeder ──► _init_process_mode()                   │
        │                                              │
  AttributeClassifier ──► _init_process_mode()         │
                                                       │
  Controller ──► ServerProcessManager ──► mp.Process (uvicorn)
        │                │
        │                └── _frame_queue (mp.Queue)
        │                         │
        └── publish_frame() ──────┘
                                  │
                           FrameBroker
                           set_ipc_queue()
                           _ipc_listener_loop()
```

---

## Жизненный цикл процессов

![Жизненный цикл процесса](images/mp_process_lifecycle.png)

**Что изображено**: диаграмма состояний (state diagram) дочернего процесса
от создания до завершения.

Состояния и переходы:
1. **Created** — `mp.Process()` создан, но ещё не запущен
2. **Starting** → `process.start()` — OS создаёт новый процесс (fork/spawn)
3. **Initializing** — выполняется `_init_logger()` + `init_worker()`
   (загрузка модели). Если `init_worker()` бросает исключение → **Failed**
4. **Ready** — логирует `"Process {name} ready"`, входит в основной цикл
5. **Processing** — цикл `input_queue.get()` → `worker_impl()` → `output_queue.put()`.
   Переходы: получен `None` (poison pill) → **Stopping**;
   `_stop_event.is_set()` → **Stopping**; необработанное исключение → **Crashed**
6. **Stopping** — выполняется `cleanup()` (освобождение GPU, закрытие сессий)
7. **Exited** — процесс завершён с `exitcode=0`
8. **Crashed** — процесс завершён с `exitcode!=0`. Health Monitor обнаруживает
   это и переводит в **Restarting** → новый процесс начинает с **Created**

---

## Кросс-процессное логирование

Дочерние процессы не могут писать в файлы логов родительского процесса
напрямую (разные файловые дескрипторы). Каждый `MpControl` создаёт свою
`_log_queue` и запускает listener thread в родительском процессе. Все
`MpWorker` получают эту очередь и настраивают `logging.handlers.QueueHandler`
при старте.

![Кросс-процессное логирование](images/mp_cross_process_logging.png)

**Что изображено**: схема пересылки логов из дочерних процессов в
основной процесс.

Компоненты:
- **Child Process 1..N** — каждый дочерний процесс имеет свой `logging.Logger`,
  к которому подключён `QueueHandler`. Все `LogRecord` отправляются в
  `_log_queue` (`mp.Queue`), а не в файл/консоль
- **_log_queue** (`mp.Queue`) — межпроцессная очередь, через которую
  `LogRecord` объекты передаются из дочерних процессов в основной
- **Log Listener Thread** — `threading.Thread` в основном процессе,
  который в бесконечном цикле читает `LogRecord` из `_log_queue`
  и передаёт их в стандартную систему логирования Python:
  `logging.getLogger(record.name).handle(record)`
- **Main Process Logger** — стандартный логгер основного процесса,
  который пишет в файл и/или консоль

Результат: логи из всех дочерних процессов появляются в общем лог-файле
с правильными именами логгеров (например, `evileye.mp_worker.det-mp-0-worker`),
уровнями и timestamps. Оператор видит единый поток логов.

---

## Обратная совместимость

Система полностью обратно совместима:

1. **Если `execution_mode` не указан** — используется `"thread"` (старое поведение)
2. **Старые конфиги работают без изменений** — ни один существующий параметр не удалён
3. **Интерфейс `put()`/`get()` не изменился** — `ProcessorStep`, `ProcessorFrame`
   и остальные оркестраторы не знают о режиме выполнения
4. **`ObjectDetectorYoloMp`** — старый класс для явного мультипроцессного детектора
   по-прежнему работает, но теперь рекомендуется использовать
   `ObjectDetectorYolo` + `"execution_mode": "process"`

### Миграция

Для перехода на мультипроцессность достаточно добавить одну строку
в секцию нужного компонента:

```diff
  "detectors": [
      {
          "model": "models/yolo11n.pt",
          "source_ids": [0],
+         "execution_mode": "process"
      }
  ]
```

---

## Переменные окружения и единый стриминг (Config Run)

Когда пайплайн запускается как Config Run (отдельный OS-процесс), для стриминга
нужно как-то передавать JPEG-кадры из дочернего процесса обратно в API-сервер.
Для этого используется файловый IPC: дочерний процесс пишет кадры в файл на диске,
а API-сервер их оттуда читает.

### Переменные окружения

| Переменная | Кто задает | Кто читает | Для чего |
|------------|------------|------------|----------|
| **`EVILEYE_PIPELINE_ID`** | `ConfigRunManager` при старте дочернего процесса (значение `rid`) | `Controller` в дочернем процессе | Идентификатор пайплайна. Используется как `stream_pipeline_id` и как ключ в FrameBroker на стороне сервера |
| **`EVILEYE_FRAME_DIR`** | `ConfigRunManager` при старте дочернего процесса | `Controller` в дочернем процессе | Путь к временной директории (например `/tmp/evileye_frames/1/`), куда Controller записывает файл `latest.jpg` с последним обработанным кадром |
| **`PYTHONUNBUFFERED`** | `ConfigRunManager` при старте дочернего процесса | Python runtime | Установлена в `1` для того чтобы логи дочернего процесса не буферизировались и были видны в реальном времени |

Эти переменные задаются только при запуске Config Run через API. При ручном запуске
`process.py` или при in-process пайплайне они отсутствуют, и Controller публикует
кадры в локальный FrameBroker (или через `ServerProcessManager` если веб-сервер
запущен в отдельном процессе).

### Как это работает

1. Клиент создает Config Run: `POST /api/v1/configs/runs`, затем запускает его:
   `POST /api/v1/configs/runs/{rid}/start`.
2. **ConfigRunManager.start(rid)** создает временную директорию
   `/tmp/evileye_frames/{rid}/`, записывает путь в переменную окружения
   `EVILEYE_FRAME_DIR` и запускает `process.py` с этим окружением.
   Одновременно запускается `_FramePoller` для этого `rid`.
3. В дочернем процессе **Controller** на каждом кадре:
   - кодирует кадр в JPEG через `cv2.imencode`
   - записывает его во временный файл `.latest.tmp`
   - атомарно переименовывает `.latest.tmp` в `latest.jpg` (через `Path.replace`)
4. В API-сервере **_FramePoller** (фоновый поток в `ConfigRunManager`) каждые ~40мс
   проверяет `mtime` файла `latest.jpg`. Если файл обновился, читает его и вызывает
   `broker.publish_jpeg(str(rid), data)`.
5. Клиент запрашивает стрим: **GET /api/v1/pipelines/{rid}/stream.mjpg** или снимок:
   **GET /api/v1/pipelines/{rid}/snapshot**.
6. Эндпоинты стриминга вызывают `_resolve_pipeline(rid)`, который проверяет
   `ConfigRunManager` и возвращает `str(rid)` как ключ FrameBroker.
7. FrameBroker отдает последний кадр, и стриминг работает.

При остановке Config Run `_FramePoller` перестает следить за директорией,
и она удаляется.

```
Дочерний процесс                   API-сервер
      |                                  |
  cv2.imencode → jpeg                    |
      |                                  |
  write /tmp/evileye_frames/{rid}/       |
        latest.jpg (atomic rename)       |
      |                                  |
      |        _FramePoller (~40ms)      |
      |        stat → mtime changed? --->|
      |        read_bytes --------> publish_jpeg
      |                                  |
      |                           FrameBroker
      |                                  |
      |                           GET /stream.mjpg
      |                           → latest_jpeg(rid)
```

### Схемы

**Поток данных при едином стриминге для Config Run:**

![Поток данных: единый стриминг для Config Run](images/mp_unified_streaming_flow.jpeg)

**Назначение переменных окружения:**

![Переменные окружения для Config Run](images/mp_env_variables.jpeg)

---

## Рекомендации

| Сценарий | Рекомендация |
|----------|-------------|
| Одна камера, лёгкая модель | `"thread"` — overhead от IPC не оправдан |
| Несколько камер, тяжёлая модель (YOLOv8x) | `"process"` для детекции |
| GPU-детекция + CPU-трекинг с ReID | `"process"` для обоих |
| Веб-сервер с множеством клиентов | `"process"` для сервера |
| Отладка / разработка | `"thread"` — проще дебажить |

### Ограничения

- ML-модели **нельзя передать между процессами** (pickle не работает с GPU-тензорами).
  Каждый воркер загружает модель самостоятельно в `init_worker()`
- Передача данных через `mp.Queue` использует pickle-сериализацию,
  что добавляет overhead (~1-5 мс на кадр)
- На Windows `multiprocessing` использует `spawn` (не `fork`),
  поэтому каждый дочерний процесс импортирует все модули заново

---

## Каталог диаграмм

Все диаграммы хранятся в `docs/images/` и встроены в соответствующие
разделы документа. Ниже — полный перечень с описанием и ссылками на
разделы, где они используются.

| # | Файл | Описание | Раздел |
|---|------|----------|--------|
| 1 | [`mp_gil_comparison.png`](images/mp_gil_comparison.png) | Сравнение Threading vs Multiprocessing: почему потоки не дают параллелизма из-за GIL, а процессы — дают | [Проблема GIL](#проблема-gil) |
| 2 | [`mp_architecture.png`](images/mp_architecture.png) | Общая архитектура: основной процесс (Controller, Pipeline, GUI) и дочерние процессы (Detection, Tracking, Attributes, Web Server), связанные через mp.Queue | [Архитектура решения](#общая-схема) |
| 3 | [`mp_dispatcher_pattern.png`](images/mp_dispatcher_pattern.png) | Паттерн Dispatcher Thread: как данные проходят Pipeline → Dispatcher → mp.Queue → Child Process → mp.Queue → Dispatcher → Pipeline | [Паттерн Dispatcher Thread](#паттерн-dispatcher-thread) |
| 4 | [`mp_seq_init.png`](images/mp_seq_init.png) | Sequence: инициализация компонента в process mode — от set_params() до загрузки модели в дочернем процессе | [Диаграмма 1](#1-инициализация-компонента-в-режиме-process) |
| 5 | [`mp_seq_frame_processing.png`](images/mp_seq_frame_processing.png) | Sequence: путь одного кадра через детекцию в процессном режиме — Source → ProcessorStep → Dispatcher → MpWorkerYolo → результат | [Диаграмма 2](#2-обработка-кадра-детекция-в-процессе) |
| 6 | [`mp_seq_full_pipeline.png`](images/mp_seq_full_pipeline.png) | Sequence: полный пайплайн — кадр проходит через все этапы (детекция → трекинг → ROI → атрибуты → визуализация), каждый в своём процессе | [Диаграмма 3](#3-полный-пайплайн-с-мультипроцессностью) |
| 7 | [`mp_seq_shutdown.png`](images/mp_seq_shutdown.png) | Sequence: graceful shutdown — poison pill → stop_event → join → terminate → kill для каждого компонента | [Диаграмма 4](#4-graceful-shutdown) |
| 8 | [`mp_seq_auto_restart.png`](images/mp_seq_auto_restart.png) | Sequence: health monitor обнаруживает упавший процесс и автоматически перезапускает его | [Диаграмма 5](#5-автоматический-перезапуск-упавшего-воркера) |
| 9 | [`mp_seq_web_server.png`](images/mp_seq_web_server.png) | Sequence: IPC между Controller и веб-сервером — JPEG-кадры передаются через mp.Queue в FrameBroker дочернего процесса | [Диаграмма 6](#6-веб-сервер-в-отдельном-процессе-ipc-через-mpqueue) |
| 10 | [`mp_process_lifecycle.png`](images/mp_process_lifecycle.png) | State diagram: жизненный цикл дочернего процесса — Created → Starting → Initializing → Ready → Processing → Stopping → Exited (или Crashed → Restarting) | [Жизненный цикл процессов](#жизненный-цикл-процессов) |
| 11 | [`mp_cross_process_logging.png`](images/mp_cross_process_logging.png) | Схема кросс-процессного логирования: QueueHandler в дочерних процессах → mp.Queue → Log Listener Thread → стандартный Logger основного процесса | [Кросс-процессное логирование](#кросс-процессное-логирование) |
| 12 | [`mp_unified_streaming_flow.jpeg`](images/mp_unified_streaming_flow.jpeg) | Поток данных при едином стриминге для Config Run: дочерний процесс пишет JPEG в файл, _FramePoller читает и публикует в FrameBroker, стриминг отдает кадры клиенту | [Переменные окружения и единый стриминг](#переменные-окружения-и-единый-стриминг-config-run) |
| 13 | [`mp_env_variables.jpeg`](images/mp_env_variables.jpeg) | Назначение переменных окружения EVILEYE_PIPELINE_ID и EVILEYE_FRAME_DIR для Config Run | [Переменные окружения и единый стриминг](#переменные-окружения-и-единый-стриминг-config-run) |

---

## FAQ

### Куда именно в JSON-конфиге писать `execution_mode`?

Параметр `"execution_mode"` пишется **внутрь секции конкретного компонента**,
на одном уровне с его остальными параметрами. Вот карта конфигурации:

```json
{
    "pipeline": {
        "sources": [{ ... }],              // <-- НЕ поддерживает execution_mode
        "preprocessors": [{ ... }],        // <-- НЕ поддерживает execution_mode

        "detectors": [{
            "model": "models/yolo11n.pt",
            "source_ids": [0],
            "execution_mode": "process"    // <-- СЮДА, рядом с model и source_ids
        }],

        "trackers": [{
            "source_ids": [0],
            "execution_mode": "process",   // <-- СЮДА, рядом с source_ids
            "botsort_cfg": { ... }
        }],

        "mc_trackers": [{ ... }],          // <-- НЕ поддерживает execution_mode

        "attributes_roi": [{
            "source_ids": [0],
            "execution_mode": "process"    // <-- СЮДА
        }],

        "attributes_classifier": [{
            "model": "models/attr.pt",
            "source_ids": [0],
            "execution_mode": "process"    // <-- СЮДА
        }]
    },

    "server": {
        "enabled": true,                   // <-- обязательно true, иначе не запустится
        "execution_mode": "process",       // <-- СЮДА, на уровне server
        "host": "0.0.0.0",
        "port": 8080
    },

    "controller": { ... },                // <-- НЕ поддерживает execution_mode
    "objects_handler": { ... },            // <-- НЕ поддерживает execution_mode
    "events_detectors": { ... }            // <-- НЕ поддерживает execution_mode
}
```

**Правило**: `execution_mode` пишется только в те секции, где есть тяжёлые
вычисления (детекция, трекинг, атрибуты, веб-сервер). Sources, preprocessors,
events и controller всегда работают в потоках.

### Как запускается веб-сервер? Нужна отдельная команда?

Есть **два способа** запустить веб-сервер:

| Способ | Команда | Когда использовать |
|--------|---------|-------------------|
| **Отдельно** | `evileye server --port 8080` | API-сервер управляет пайплайнами через REST. Стандартный режим |
| **Вместе с пайплайном** | `evileye run config.json` + `server.enabled: true` | Controller сам поднимает сервер в отдельном процессе. Удобно для standalone-режима |

При `evileye server`:
- Сервер запускается как основной процесс
- Пайплайны создаются/запускаются через REST API (`POST /api/v1/configs/runs`)
- Кадры из дочерних процессов попадают в сервер через файловый IPC (`_FramePoller`)
- Секция `"server"` в JSON-конфиге **не используется** (настройки передаются через CLI: `--host`, `--port`)

При `evileye run` + `server.enabled: true`:
- Controller запускает FastAPI/Uvicorn в **дочернем процессе** (если `execution_mode: "process"`)
- Кадры передаются через `mp.Queue` автоматически
- Секция `"server"` в JSON-конфиге **используется**

### Что означает лог "Scheduled restart is disabled in config, running single process"?

Это **не связано с мультипроцессностью**. Это существующая функция
автоматического перезапуска системы по расписанию (для борьбы с утечками
памяти при длительной работе).

Настраивается в секции `controller.scheduled_restart`:

```json
"controller": {
    "scheduled_restart": {
        "enabled": false,
        "mode": "daily_time",
        "time": "01:00"
    }
}
```

Если секция отсутствует или `enabled: false` — в логе появляется сообщение
`"Scheduled restart is disabled"`. Это нормальное информационное сообщение,
не ошибка.


### Как убедиться, что компонент действительно запустился в отдельном процессе?

Ищите в логах следующие строки:

| Компонент | Строка в логе |
|-----------|-------------|
| Детекция | `Detection initialized in PROCESS mode with N worker(s)` |
| Детекция | `Started worker process pid=XXXX` |
| Детекция | `Process det-mp-0-worker ready` |
| Трекинг | `Started worker process pid=XXXX` |
| Трекинг | `Process tracker-...-worker ready` |
| Веб-сервер | `Web server process started, pid=XXXX` |

Если вместо этого вы видите обычные сообщения о потоках — значит
`execution_mode` не был прочитан или указан неправильно.

### Можно ли комбинировать thread и process в одном конфиге?

Да, **каждый компонент настраивается независимо**. Например:

```json
"detectors": [{ "execution_mode": "process" }],
"trackers": [{ "execution_mode": "thread" }]
```

Здесь детекция работает в отдельном процессе, а трекинг — в потоке.
Это может быть оптимально, если GPU-детекция — основной bottleneck,
а трекинг достаточно лёгкий.

### Как запустить пайплайн с мультипроцессностью через REST API?

Пошаговая инструкция с конкретными HTTP-запросами. Предполагается, что
сервер запущен через `evileye server --host 0.0.0.0 --port 8080`.

---

**Шаг 1. Запустить сервер**

```bash
evileye server --host 0.0.0.0 --port 8080
```

Сервер поднимается, Swagger UI доступен по адресу `http://localhost:8080/docs`.

---

**Шаг 2. (Опционально) Посмотреть доступные конфиги**

```
GET /api/v1/configs
```

```bash
curl http://localhost:8080/api/v1/configs
```

Ответ:

```json
["single_video.json", "single_video_multiprocess.json", "multi_videos.json"]
```

---

**Шаг 3. (Опционально) Посмотреть содержимое конфига**

```
GET /api/v1/configs/{name}
```

```bash
curl http://localhost:8080/api/v1/configs/single_video_multiprocess.json
```

Ответ — полный JSON-конфиг. Убедитесь, что в нём есть `"execution_mode": "process"`
в нужных секциях.

---

**Шаг 4. Создать Config Run**

```
POST /api/v1/configs/runs
```

Два варианта — по имени файла или с телом конфига:

**Вариант A — по имени файла из `configs/`:**

```bash
curl -X POST http://localhost:8080/api/v1/configs/runs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-mp-pipeline",
    "config_name": "single_video_multiprocess.json"
  }'
```

**Вариант B — с полным телом конфига (inline):**

```bash
curl -X POST http://localhost:8080/api/v1/configs/runs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-mp-pipeline",
    "config_body": {
      "pipeline": {
        "pipeline_class": "PipelineSurveillance",
        "sources": [{
          "camera": "videos/planes_sample.mp4",
          "source": "VideoFile",
          "source_ids": [0]
        }],
        "detectors": [{
          "model": "models/yolo11n.pt",
          "source_ids": [0],
          "execution_mode": "process"
        }],
        "trackers": [{
          "source_ids": [0],
          "execution_mode": "process"
        }]
      },
      "controller": {
        "fps": 30,
        "class_names": ["person", "car"]
      }
    }
  }'
```

Ответ:

```json
{
  "id": 1,
  "name": "my-mp-pipeline",
  "config_path": "configs/my-mp-pipeline.json",
  "pid": null,
  "state": "created",
  "error": null
}
```

Запомните `id` (в данном случае `1`) — он нужен для следующих шагов.

---

**Шаг 5. Запустить Config Run**

```
POST /api/v1/configs/runs/{rid}/start
```

```bash
curl -X POST http://localhost:8080/api/v1/configs/runs/1/start
```

Ответ:

```json
{
  "id": 1,
  "name": "my-mp-pipeline",
  "config_path": "configs/my-mp-pipeline.json",
  "pid": 12345,
  "state": "running",
  "error": null
}
```

Что происходит внутри:
1. `ConfigRunManager.start()` создает временную директорию для кадров
   (`/tmp/evileye_frames/{rid}/`) и запускает `process.py --config ... --no-gui`
   как отдельный OS-процесс через `subprocess.Popen`. В окружение передаются
   `EVILEYE_PIPELINE_ID`, `EVILEYE_FRAME_DIR`, `PYTHONUNBUFFERED=1`
2. Запускается `_FramePoller` для этого `rid`, который будет следить за файлом
   `latest.jpg` в этой директории
3. `process.py` создает `Controller`, который читает конфиг
4. Controller инициализирует каждый компонент пайплайна
5. Для компонентов с `"execution_mode": "process"` создаются `MpControl` +
   дочерние процессы (MpWorkerYolo, MpWorkerTracker и т.д.)
6. Пайплайн начинает обрабатывать видео, кадры записываются в `latest.jpg`

---

**Шаг 6. Проверить статус**

```
GET /api/v1/configs/runs/{rid}
```

```bash
curl http://localhost:8080/api/v1/configs/runs/1
```

Ответ:

```json
{
  "id": 1,
  "name": "my-mp-pipeline",
  "config_path": "configs/my-mp-pipeline.json",
  "pid": 12345,
  "state": "running",
  "error": null
}
```

Возможные значения `state`:
- `created` — создан, но не запущен
- `starting` — запускается
- `running` — работает
- `stopping` — останавливается
- `stopped` — остановлен
- `error` — ошибка (см. поле `error`)

---

**Шаг 7. Смотреть видеопоток (MJPEG)**

```
GET /api/v1/pipelines/{rid}/stream.mjpg?fps=5
```

Откройте в браузере:

```
http://localhost:8080/api/v1/pipelines/1/stream.mjpg?fps=5
```

Или получите один кадр:

```
GET /api/v1/pipelines/{rid}/snapshot
```

```bash
curl http://localhost:8080/api/v1/pipelines/1/snapshot --output frame.jpg
```

---

**Шаг 8. Остановить Config Run**

```
POST /api/v1/configs/runs/{rid}/stop
```

```bash
curl -X POST http://localhost:8080/api/v1/configs/runs/1/stop
```

Ответ:

```json
{
  "id": 1,
  "name": "my-mp-pipeline",
  "pid": null,
  "state": "stopped",
  "error": null
}
```

Что происходит внутри:
1. `ConfigRunManager.stop()` отправляет `SIGTERM` процессу `process.py`
2. `process.py` перехватывает сигнал, вызывает `Controller.stop()`
3. Controller останавливает каждый компонент: `detector.stop()` → `mp_control.stop()`
4. `MpControl` отправляет poison pill каждому воркеру, ждёт завершения
5. Если процесс не завершился за 2 секунды — `SIGKILL`

---

**Шаг 9. (Опционально) Удалить Config Run**

```
DELETE /api/v1/configs/runs/{rid}
```

```bash
curl -X DELETE http://localhost:8080/api/v1/configs/runs/1
```

---

мультипроцессность настраивается **в конфиге**, а не
в API-запросе. API просто передаёт конфиг в `process.py`, который создаёт
Controller. Controller читает `execution_mode` из конфига и решает,
запускать компонент в потоке или процессе. API об этом не знает.
