## Обновление: plan completion sweep (2026-05-21)

- `EventImageWriter` + PG adapters; `botsort_config.py`; subprocess YOLO test; stream_player conftest.
- Исправлен импорт `CaptureDeviceType` в `gstreamer_capture_frames.py` (регрессия после split).
- KPI-gate: `reports/ipc_kpi_gate_20260521_145543/report.md` — **PASS** (`single_video_multiprocess`, `poly-videos-gst`).
- `TECH_DEBT.md`: TD-011–TD-017 закрыты; Open пуст.

## Обновление: KPI-gate профиль + Этап 3 (runtime DI)

- Добавлен профиль порогов KPI-gate: `configs/kpi_gate_profile.json`.
- `scripts/run_ipc_kpi_gate.py` теперь:
  - читает профиль (`--profile`, по умолчанию `configs/kpi_gate_profile.json`),
  - применяет `configs` и `thresholds` из профиля,
  - пишет в `summary.json` информацию о примененном профиле.
- `scripts/benchmark_ipc_kpi.py` расширен метриками:
  - `pipeline_samples`,
  - `capture_fps_samples`,
  - проверка минимального числа сэмплов `--min-pipeline-samples`.
- Проверочный прогон KPI-gate:
  - `reports/ipc_kpi_gate_20260414_180646/report.md`
  - статус: `PASS` для `single_video_multiprocess` и `poly-videos-gst`.

- Этап 3 (декомпозиция runtime-менеджеров / унификация DI), шаг 1:
  - в `evileye/core/runtime_context.py` добавлены универсальные API:
    - `get_runtime_service`,
    - `set_runtime_service`,
    - `get_or_create_runtime_service`.
  - `evileye/api/core/broker_access.py`, `evileye/api/core/manager_access.py`,
    `evileye/core/process_manager.py` переведены с module-level singleton-переменных
    на единый runtime-контекст через `get_or_create_runtime_service`.
  - Добавлены unit-тесты:
    - `tests/unit/core/test_runtime_context_services.py`.
  - В `evileye/run_config_helper.py` добавлен `reset_runtime_context()` в shutdown-path,
    чтобы runtime-синглтоны не протекали между последовательными прогонами.

- Этап 3, шаг 2 (унификация DI controller services):
  - `evileye/controller/services/service_locator.py` переведен на `DIContainer`:
    - централизованная регистрация singleton-фабрик для controller services,
    - получение сервисов через контейнер вместо ручного `new` в каждом `if`,
    - `register_*` методы синхронизируют состояние и в локаторе, и в контейнере.
  - Добавлены unit-тесты:
    - `tests/unit/controller/services/test_service_locator_di.py`
      (создание сервисов через контейнер и idempotent-поведение `create_all_services`).

- Этап 3, шаг 3 (убраны прямые global-access зависимости вне API-access модулей):
  - Добавлен `evileye/core/runtime_services.py` как единая точка доступа к runtime service-инстансам:
    - `get_frame_broker()`
    - `get_pipeline_manager()`
  - Переведены модули на `runtime_services` вместо прямого импорта `api.core.*_access`:
    - `evileye/server.py`
    - `evileye/controller/services/streaming_service.py`
    - `evileye/api/core/pipeline_manager.py`
    - `evileye/api/core/config_run_manager.py`
    - `evileye/api/core/server_state.py`
    - `evileye/api/routes/streaming.py`
    - `evileye/api/routes/internal.py`
  - `evileye/api/core/broker_access.py` и `evileye/api/core/manager_access.py` оставлены как совместимые фасады поверх `runtime_services`.
  - Удален неиспользуемый импорт `get_manager` из `evileye/api/app.py`.
  - Дополнен `tests/unit/core/test_runtime_context_services.py` проверкой согласованности wrapper-функций.

- Этап 3, шаг 4 (финализация интерфейсов доступа к runtime services):
  - `evileye/api/core/broker_access.py` и `evileye/api/core/manager_access.py` помечены как
    compatibility-facades с `DeprecationWarning` (однократно), чтобы мягко мигрировать код.
  - Единый рекомендованный API закреплен в `evileye/core/runtime_services.py`
    и переэкспортирован через `evileye/core/__init__.py`.
  - Добавлен тест на deprecation-поведение:
    - `tests/unit/core/test_runtime_context_services.py::test_compat_accessors_emit_deprecation_warning_once`.

## Обновление: устранение узкого места детекции в multiprocessing

- Диагностика показала, что горячий путь `pipeline -> detector dispatcher` в `ObjectDetectorBase`
  использовал `multiprocessing.Queue` даже при локальном (внутрипроцессном) обмене между
  шагом пайплайна и detector-thread dispatcher.
- Это давало избыточные IPC/serialization накладные расходы и высокий stage-time у `detectors`.
- Исправление:
  - `evileye/object_detector/object_detection_base.py`:
    - `_init_queues()` переведен на `queue.Queue` для `queue_in/queue_out/queue_dropped_id`
      независимо от `execution_mode`;
    - реальная process-граница остается внутри `DetectionThreadYoloMp` через `MpControl`.
- Добавлен unit-тест:
  - `tests/unit/object_detector/test_detector_queue_mode.py`
    - проверяет, что в `execution_mode=process` используются thread-queues.
- Повторный perf-прогон `configs/single_video_multiprocess.json`:
  - до: `detectors avg=104.43ms, p95=415.00ms`
  - после: `detectors avg=14.56ms, p95=49.80ms`
  - общий pipeline: `avg=105.38ms -> 18.47ms`, `p95=415.90ms -> 85.80ms`

# Прогресс рефакторинга EvilEye

## Выполнено (95%)

### ✅ Этап 1: Интерфейсы и абстракции (100%)
- Все интерфейсы созданы и реализованы
- Контракты определены

### ✅ Этап 2: Разделение Controller на сервисы (95%)
- Все сервисы созданы и интегрированы
- Controller использует сервисы для инициализации
- Метод `run()` рефакторирован на небольшие методы (с ~150 до ~50 строк основного цикла)

### ✅ Этап 3: Улучшение инкапсуляции (95%)
- Visualizer инкапсулирован
- ObjectsHandler инкапсулирован
- Фасады созданы

### ✅ Этап 4: Dependency Injection (90%)
- DIContainer создан
- DependencyRegistry создан
- Прямые импорты убраны из ObjectsHandler и Visualizer (используется TYPE_CHECKING)
- Циклические зависимости устранены

### ✅ Этап 5: Оптимизация производительности (95%)
- Оптимизация памяти (deepcopy → copy/list) во всех адаптерах БД
- **ObjectPool интегрирован в hot-path обработки** ✅
  - Используется для ObjectResult и ObjectResultHistory
  - Автоматический возврат объектов в пул при удалении
  - Настраивается через параметры (use_object_pool, object_pool_size)
- Батчинг БД: базовая инфраструктура добавлена (batch_size, batch_timeout)

### ✅ Этап 6: Улучшение стиля кодирования (85%)
- Type hints добавлены в новые модули
- Валидация конфигураций интегрирована
- Методы разбиты на более мелкие
- Улучшена читаемость кода

## Осталось выполнить (опционально)

### ⚠️ Полная реализация батчинга БД (30%)
- Базовая инфраструктура добавлена (batch_size, batch_timeout)
- Требуется реализация группировки запросов в _execute_query
- Требуется использование executemany или VALUES для батчевых вставок

### ⚠️ Дальнейший рефакторинг Controller (10%)
- Метод run() разбит на методы, но Controller все еще большой (~2000 строк)
- Можно вынести логику обработки событий в отдельный ProcessingService

## Метрики

- Создано новых файлов: 15+
- Изменено файлов: 35+
- Уменьшено строк в Controller.run(): ~150 → ~50 (основной цикл)
- Убрано прямых импортов: 2 (ObjectsHandler, Visualizer)
- Добавлено методов инкапсуляции: 5+
- **Интегрирован ObjectPool**: переиспользование ObjectResult и ObjectResultHistory в hot-path
- **Оптимизировано создание объектов**: до 20 объектов в пуле для переиспользования

## Следующие шаги

1. Интегрировать ObjectPool в ObjectsHandler для переиспользования ObjectResult
2. Реализовать полный батчинг в _execute_query для DatabaseAdapterObjects
3. Рассмотреть создание ProcessingService для логики обработки в run()

## Обновление 2026-04-14 (multiprocessing / ipc modes)

- Добавлен верхнеуровневый параметр конфига `pipeline.ipc_mode` в рабочих конфигах:
  - `configs/single_video_multiprocess.json`
  - `configs/poly-videos-gst.json`
- Нормализация режимов добавлена в `PipelineSurveillance`:
  - секции получают `ipc_mode` и дефолтный `execution_mode=thread`, если поле отсутствует.
- Добавлены capability metadata в `EvilEyeBase` + валидация stage-level совместимости в `ProcessorBase`.
- Добавлен runtime-scoped контекст `RuntimeContext` и привязка manager/broker/process_manager accessors.
- Убраны busy-wait паттерны в процессных dispatch loop:
  - `object_tracking_base`, `roi_feeder`, `attribute_classifier`.
- ROI flow переведен на легковесный payload:
  - вместо `roi_image` передается `roi_bbox`, crop выполняется ближе к классификатору.
- Добавлен базовый shared-memory transport:
  - `evileye/core/frame_transport.py` (`FrameHandle`, `SharedFrameTransport`).

### Прогоны и анализ

- Прогон unit-тестов:
  - `tests/unit/pipeline/test_pipeline_mode_config.py`
  - `tests/unit/attributes/test_roi_bbox_payload.py`
  - `tests/unit/pipeline/test_frame_transport.py`
- Smoke прогоны реальных конфигов:
  - `configs/single_video_multiprocess.json`
  - `configs/poly-videos-gst.json`
- Проверены console/logs (`logs/20260414_163914_evileye_main.log`, `logs/20260414_164058_evileye_main.log`):
  - обнаружены shutdown проблемы в multiprocess режиме (`Force-killing worker`, stop timeout),
  - есть известные предупреждения (LabelingManager preload, TensorRT fallback).

## Обновление 2026-04-14 (доработки по чеклисту незакрытых шагов)

### Что доработано

- Добавлены runtime-метрики в multiprocessing-контур:
  - `MpControl.get_metrics()` теперь отдает `put_calls_total`, `put_wait_ms_total`,
    `avg_put_wait_ms`, `get_calls_total`, `worker_restart_total`,
    `restart_suppressed_total`, `input_queue_size`, `output_queue_size`, `alive_workers`.
  - `MpWorker` пишет итоговые worker-метрики при выходе:
    `processed_total`, `drops_total`, `avg_put_wait_ms`.
- Добавлен базовый adapter `standard<->descriptor` в `ProcessorStep`:
  - best-effort materialization кадра из `frame_handle` для стадий,
    где `requires_materialized_frame=True`.
- Доработан preprocessing-контур (`PreprocessingBase`):
  - убран busy-wait (`sleep(0.01)`),
  - введен bounded `queue_out`,
  - добавлена безопасная drop-oldest логика на очередях,
  - добавлен best-effort materialization через `frame_handle`,
  - объявлены capability metadata (`accepts_frame_handle`, `emits_dto_type`, `requires_materialized_frame`).
- Доработан mc-tracker контракт (`custom_object_tracking`):
  - в эмит добавляется lightweight `batch_meta`:
    `payload_version`, `source_id`, `frame_id`, `batch_age_ms`, `is_partial`,
  - добавляется `frame_ref`, если доступен.

### Добавленные тесты

- `tests/unit/core/test_mp_control_metrics.py`
- `tests/unit/preprocessing/test_preprocessing_base_contract.py`
- `tests/unit/object_multi_camera_tracker/test_batch_meta.py`
- `tests/unit/pipeline/test_processor_step_adapter.py`

### Прогоны и логи

- Unit suite (13 тестов) пройден:
  - включает новые тесты + ранее добавленные
    (`test_mp_restart_policy_config`, `test_pipeline_mode_config`,
     `test_roi_bbox_payload`, `test_frame_transport`).
- Smoke:
  - `configs/single_video_multiprocess.json` (успешный старт/останов),
  - `configs/poly-videos-gst.json` (успешный старт/останов).
- Логи проверены:
  - `logs/20260414_172611_evileye_main.log`,
  - `logs/20260414_172655_evileye_main.log`.
- Наблюдения:
  - политика suppress restart по `-15` работает;
  - остались известные предупреждения:
    `Processor stop timeout` для tracker stop path,
    `LabelingManager _preload_existing_data`,
    `TensorRT fallback`.

## Обновление 2026-04-14 (descriptor-contract и KPI-бенч)

### Descriptor-contract (доработано)

- Добавлен модуль контрактов `evileye/core/ipc_contracts.py`:
  - `BatchMeta` (typed object),
  - `attach_frame_contract()` для frame-level metadata.
- `PreprocessingBase` теперь стабильно работает в descriptor-friendly режиме:
  - выставляет frame-level metadata (`payload_version`, `frame_ref`),
  - сохраняет совместимость с `standard` payload.
- `ObjectMultiCameraTracking` расширен контрактом выдачи:
  - `batch_meta` (dict),
  - `batch_meta_obj` (`BatchMeta`),
  - `frame_ref` (если доступен).
- В `ProcessorStep` добавлен adapter `standard<->descriptor`
  (best-effort materialization по `frame_handle` для стадий, где требуется image).

### KPI benchmark tooling

- Добавлен скрипт:
  - `scripts/benchmark_ipc_kpi.py`
  - сравнивает baseline/candidate логи по KPI:
    `warnings`, `errors`, `tracebacks`, `worker restarts`,
    `suppressed restarts`, `stop timeouts`, `force-kills`.
- Сформирован отчёт:
  - `reports/ipc_kpi_2026-04-14_post.md`
  - результат сравнения `logs/20260414_164906_evileye_main.log` vs
    `logs/20260414_173200_evileye_main.log`:
    - `Worker restarts: 4 -> 0`,
    - `Errors: 1 -> 0`,
    - `Force-kills: 1 -> 0`,
    - `Warnings: 14 -> 9`.

### Тесты и прогоны

- Unit-тесты: `13 passed` (включая новые для adapter/contract/metrics).
- Smoke:
  - `configs/single_video_multiprocess.json` — успешный старт/останов.
  - `configs/poly-videos-gst.json` — успешный старт/останов.

## Обновление 2026-04-14 (продолжение закрытия PR-2.3/2.6/2.7)

### PR-2.3 (preprocessing contract) — расширено

- `PreprocessingPipeline` теперь поддерживает policy-параметры:
  - `in_place_allowed`
  - `copy_required`
- Добавлен `frame_version` инкремент после preprocessing.
- Сохранена совместимость со `standard` pipeline.
- Тест:
  - `tests/unit/preprocessing/test_preprocessing_pipeline_policy.py`

### PR-2.6 (mc-tracker contract) — расширено

- Добавлен typed DTO:
  - `evileye/core/tracking_dto.py` (`TrackingDTO`, `TrackingObjectDTO`)
- В `custom_object_tracking` к результату прикрепляется:
  - `tracking_dto`
  - уже существующие `batch_meta`/`batch_meta_obj`/`frame_ref` сохранены.
- Тест дополнен:
  - `tests/unit/object_multi_camera_tracker/test_batch_meta.py`

### PR-2.7 (KPI tooling) — расширено

- `scripts/benchmark_ipc_kpi.py` расширен метриками:
  - `p95_pipeline_ms` (если есть `PerfDiag(Pipeline)`),
  - `pipeline_hz_est`,
  - `max_rss_mb` (по `total_memory_usage_mb` в логах).
- Новый отчёт:
  - `reports/ipc_kpi_2026-04-14_pr24_plus.md`
