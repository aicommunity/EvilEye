# План завершения миграции расширяемых модулей EvilEye

## Цель и направление

Довести встроенные компоненты и пайплайны до одного публичного Plugin SPI. Встроенные реализации остаются в репозитории и становятся контрольными примерами для внешних пакетов. `PipelineSurveillance` остаётся специализированным, но расширяемым пайплайном; `PipelineDeclarative` — простым последовательным пайплайном. В первой версии не вводить универсальный DAG, hot-plug и автоматическую установку зависимостей в работающем процессе.

Работы вести на серверной ветке `plugin_support`; каждый проверенный этап фиксировать отдельным коммитом. Пользовательские неотслеживаемые файлы не включать. До фиксации миграции этап должен иметь контрактные тесты, диагностику ошибок, запуск штатных конфигураций и подтверждённую остановку процессов.

## Текущее состояние кодовой базы

### Уже реализовано

- `evileye/core/plugins.py` содержит `PluginSpec`, `ModuleSpec`, `PipelineSpec`, `PluginRegistry` и загрузчик entry points группы `evileye.plugins`; есть проверка API version, фабрик, видов модулей, режимов и идентификаторов.
- Встроенные классы регистрируются через `register_module`; старый `EvilEyeBase.register` остаётся совместимым фасадом. Параллельный `EvilEyeBase._registry` удалён.
- `event_registry` использует общий `PluginRegistry`; встроенные и внешние event detectors перечисляются и создаются через него.
- Инвентарь закреплён тестом: 18 публичных config IDs (17 manifest modules и alias `ObjectDetectorYoloMp`); тест legacy capabilities учитывает восемь отдельных модулей с legacy backend-протоколом.
- `PipelineSurveillance` принимает `modules.<group>.mode=extend|replace`, валидирует группы и виды модулей, а `ProcessorFrame` отправляет кадр каждому совместимому процессору. `module_id` принимается наряду со старым `type`.
- `PreprocessingPipeline` и `RoiFeeder` используют `processor_item` runtime.
- Для пользовательских тревог есть `AlarmEvent`: тест проходит от внешнего event detector через controller и JSON adapter до данных журнала; проверены стабильный ID, повторная доставка, retry временной ошибки и диагностика переполнения очереди.
- Порядок штатного завершения API приведён к остановке ConfigRunManager и PipelineManager до закрытия Unix frame relay. Добавлена регрессия на порядок остановки.
- Исправлены выявленные тестами дефекты: проверка `track_id` с ключом `(source_id, track_id)`, синхронизация health process capture, обход нестабильной индексации Ultralytics Boxes в smoke test, ожидание асинхронного результата BoT-SORT и обнаружение записей в нескольких уровнях каталогов.

### Что пока остаётся legacy или отдельной реализацией

- Восемь manifest modules всё ещё заявляют `legacy_*_protocol` и используют специализированные внутренние worker/backend протоколы: два источника, три семейства детекторов (YOLO, RT-DETR, RF-DETR), BoT-SORT и два модуля атрибутов. `ObjectDetectorYoloMp` теперь только legacy config alias канонического YOLO модуля. SPI-адаптеры дают оставшимся модулям общий внешний контракт, но не заменяют их внутренние протоколы.
- `ObjectMultiCameraTracking` переведён на `kind="batch_processor"` и публичный `IBatchProcessor.process_batch(batch, state)`. Общий адаптер создаёт модуль и вызывает batch-контракт; исполнение пока только потоковое.
- Event detectors регистрируются через общий `PluginRegistry`, но жизненный цикл и подписки на `ObjectsHandler` всё ещё управляются `EventsService`; у этой стадии нет общего worker/health-контракта.
- `PipelineSurveillance`, `PipelineCapture` и `PipelineDeclarative` уже регистрируются как встроенные `PipelineSpec`. `PipelineService` разрешает их через реестр; `pipeline_class` остаётся совместимым именем. Ошибка неизвестного класса не должна переключать запуск на другой пайплайн.
- Discovery и тревоги покрыты контрактными тестами. Пример внешнего пакета уже проверен через editable install в изолированном server-side virtualenv без переустановки EvilEye.

## План оставшихся доработок

### Этап A. Уточнить контракт runtime и диагностику

1. [готово] Зафиксировать публичные структурные протоколы `processor_item`, `source`,
   `event_detector` и `batch_processor`; item/source/batch адаптеры предоставляют runtime status,
   а `ModuleRuntimeContext` передаёт state factory сериализуемые `module_id`,
   `execution_mode` и `source_ids` в потоковом и process режимах.
2. [готово] `ModuleSpec.config_schema` проверяется и нормализуется до вызова фабрики item/batch/source runtime adapters; ошибка включает qualified module ID и причину валидации. Регрессионный тест подтверждает, что фабрика не вызывается для неверной конфигурации.
3. [готово] Для `batch_processor` добавлен отдельный kind и `IBatchProcessor`; потоковая семантика явная, а `process` отвергается до запуска фабрики.
4. [готово] Для `process` проверять импортируемость factory и сериализуемость config до старта; inputs и outputs передавать через явный pickle envelope с синхронной диагностикой ошибок, а state создавать только внутри worker. Неподдержанный режим отклоняется до запуска.
6. [готово] `ModuleSpec.default_execution_mode` фиксирует режим по умолчанию; registry отвергает неподдерживаемое значение, а item/legacy/source adapters применяют заявленный режим.
5. Для очередей определить поведение по виду данных: кадры могут иметь ограниченную политику drop-oldest, тревоги должны сообщать о переполнении и ошибке сохранения.

**Проверки:** контрактные тесты создания, старта, остановки, ошибки init, исключения `process_item`, переполнения очереди, сериализации, отказа неподдерживаемого execution mode и schema errors.

### Этап B. Удалить legacy processor adapter по семействам

1. [частично] Устранён отдельный YOLO-MP manifest: `ObjectDetectorYoloMp` разрешается как config alias на `ObjectDetectorYolo`, а `execution_mode` выбирает один канонический runtime. Сам `ObjectDetectorYolo` и семейства RT-DETR/RF-DETR ещё нужно перевести на общий item runtime: вход `Frame`/DTO, состояние worker, унифицированный выход detections/debug metadata.
2. Перевести BoT-SORT на тот же контракт item processor; определить, где находится состояние трекера и как оно сбрасывается при потере/переподключении источника.
3. Перевести AttributeDetector и AttributeClassifier на item runtime после tracker stage; проверить передачу `track_id`, `source_id`, ROI и истории атрибутов.
4. После каждой группы убрать `legacy_processor_protocol` у соответствующих manifests, не удаляя compatibility `type` aliases.
5. Для каждого модуля сравнить старую и новую реализацию на фиксированных видео/кадрах: detection classes/confidence, track continuity, attributes, порядок кадров и сохранённые DTO.

**Критерий:** ни один штатный детектор, tracker или attribute module не требует `LegacyProcessorModuleAdapter`; thread/process режимы проходят один набор контрактных сценариев.

### Этап C. Мигрировать источники без потери capture-функций

1. Вынести единый `Source` контракт `open/read/close` и стандартную модель frame metadata: source, timestamp/frame_id, размеры, reconnect state и диагностические ошибки.
2. Перевести OpenCV source и затем GStreamer source на source runtime/backend, сохранив GStreamer codec fallback, reconnect, split/crop, запись сегментов, ограниченные очереди и shared-frame transport.
3. Описать отдельные source backends для `thread`/`process`; не протаскивать `execution_mode` в модуль, который фактически не исполняется в выбранном режиме.
4. При stop завершать источник и подтверждения IPC без ложных ошибок; worker failure переводит источник в visible degraded/reconnecting state.

**Проверки:** видеофайл, loop/reconnect, синтетический RTSP и доступные реальные камеры; запись и ffprobe; проверка отсутствия worker, сокетов и очередей после stop.

### Этап D. Завершить batch и event/alarm lifecycle

1. [готово] `ObjectMultiCameraTracking` использует batch SPI с явной синхронизацией и ограничением `thread`-режима; контракт покрыт unit-тестами.
2. Перевести Event detector фабрики и lifecycle с `EventsService` на PluginRegistry + общий runtime; оставить `EventsService` как управляющий слой, не второй реестр.
3. Довести `AlarmEvent` до общего контракта: type, severity, timestamp, source, details, stable ID. Проверить JSON и PostgreSQL adapters, повтор записи, недоступное хранилище и журнал UI.
4. Добавить диагностируемую остановку/переполнение, retry с ограничением и метрики очереди; отдельно решить долговечный outbox, если нужна гарантия пережить падение хоста (сейчас такой гарантии нет).

**Критерий:** внешний event/alarm detector не меняет ядро для нового события и проходит до выбранного хранилища и общего представления в журнале.

### Этап E. Свести пайплайны к реестру и проверить внешний пакет

1. [готово] `PipelineSurveillance`, `PipelineCapture` и `PipelineDeclarative` зарегистрированы как builtin `PipelineSpec`; `PipelineService` разрешает их через PluginRegistry.
2. [готово] `pipeline_class` сохранён как compatibility alias; неизвестный выбранный pipeline приводит к диагностируемой ошибке без fallback.
3. Оставить `PipelineSurveillance` фиксированным графом стадий, документировать порядок, правила `extend`/`replace`, несколько детекторов на один источник и thread-only стадии.
4. [готово] Минимальный внешний пакет установлен editable-режимом в изолированное server-side virtualenv; entry point `evileye.plugins` обнаружен, модуль зарегистрирован без изменения/переустановки EvilEye. В example package указан build backend с PEP 660 поддержкой.
5. Проверить изолированными сценариями конфликт ID, неизвестный module/pipeline, неверную API version, ошибку импорта и требования зависимостей; часть конфликтов и ошибок уже покрыта тестами реестра.

**Критерий:** builtin и внешний pipeline разрешаются тем же API; сторонний package обнаруживается после перезапуска приложения.

### Этап F. Полный regression и эксплуатационная проверка

1. Запускать `tests/unit`, затем интеграционные группы последовательно; после каждой проверки убеждаться, что дочерние multiprocessing workers завершились.
2. Обеспечить headless режим Qt тестов: при отсутствии `DISPLAY`/`WAYLAND_DISPLAY` использовать `QT_QPA_PLATFORM=offscreen`.
3. Проверить штатный видеофайл с детекцией/трекером, запись сегментов и остановку; провести отдельный запуск с RTSP камерами, не выводя URL и пароли в логи аудита.
4. Проверить Web UI и API: публичную загрузку, доступные экраны после входа и просмотр live/recorded video. Для защищённых маршрутов нужны валидные пользовательские учётные данные.
5. Снять финальный инвентарь legacy capabilities и считать миграцию завершённой только при нуле legacy протоколов либо с документированным, владельцем согласованным исключением.

## Проверки на сервере 2026-10-10

- После process serialization и `ModuleRuntimeContext` прошли целевые проверки: `tests/unit/core/test_plugin_registry.py`, `tests/unit/core/test_builtin_plugin_inventory.py`, `tests/unit/attributes/test_roi_feeder_plugin_runtime.py`, `tests/unit/preprocessing/test_preprocessing_plugin_runtime.py` и `tests/unit/preprocessing/test_preprocessing_pipeline_policy.py`. Включён тест item runtime в `thread` и `spawn process`; после pytest не осталось `pytest`, `resource_tracker` или `spawn_main` процессов.
- `tests/unit`: полный набор после изменений batch adapter и GStreamer fallback завершился с `exit=0` и дошёл до 100%; остались только warning от установленной версии Albumentations. После завершения pytest оставил 14 orphan `spawn`/`resource_tracker` процессов; их process group и `/tmp` working directory проверены, только эта тестовая группа остановлена. Targeted schema-order tests после этого также прошли.
- `tests/integration`: все тесты дошли до итогового summary: `311 passed, 42 skipped`; пропуски связаны с отсутствием локального RTSP тест-сервера, тестовой RTSP переменной/пароля, v4l2loopback и выключенными real-data тестами. После summary pytest завис на завершении multiprocessing/thread ресурсов и был остановлен таймаутом. Это остаётся эксплуатационным дефектом тестового shutdown.
- `configs/poly-cameras-gst.json` прошёл `evileye validate`. Полный запуск трёхкамерного приложения на отдельном порту поднял 3 capture, 5 detector и 5 tracker worker; Web UI root ответил HTTP 200, защищённые `/api/v1/health` и `/api/v1/state` без входа вернули 401. После SIGINT тестовый порт закрылся, оставшихся worker не найдено.
- Реальное чтение камер проверялось отдельно: OpenCV/FFmpeg получил кадры от `.200` и `.202`, `.199` кадр не отдал. В GStreamer `.200` проходит старт RTSP, а `.199` и `.202` проходят DESCRIBE/SETUP, затем камеры отвечают нестандартным `RTSP 250` на PLAY. Поэтому нельзя считать все три потока рабочими в GStreamer runtime; для двух камер требуется выяснить совместимость PLAY/transport/firmware.
- Для существующего MP4 MPEG-4 файла прямой OpenCV и прямой GStreamer `decodebin` декодировали 55 кадров. Полный `evileye run` для этой записи завершился с кодом 0: аппаратный decoder fallback и fallback на `decodebin` сработали, pipeline и capture инициализировались, ошибок capture не зарегистрировано. Root Web UI вернул 200, защищённый API — 401, тестовый порт после остановки закрылся. В этом запуске не было достоверного счётчика кадров на уровне приложения, поэтому нужно отдельно добавить/снять end-to-end подтверждение детекции на видеозаписи.
- В предыдущем system smoke видеозапись проходила через `PipelineSurveillance`, YOLO и BoT-SORT; были сохранены сегменты, `ffprobe` прочитал первый сегмент, а `MemoryAttr` показал активный объект. Последний smoke дополнительно подтвердил новый codec fallback на MPEG-4 файле.
- Пользовательский внешний пакет из `examples/plugin_package` установлен editable-режимом в отдельное virtualenv с PEP 660 backend. Discovery группы `evileye.plugins` зарегистрировал `example/add-label` с режимами `thread,process`; ядро не переустанавливалось.
- Site credentials теперь разрешаются относительно корня EvilEye даже при запуске с конфигом из другого каталога; регрессионный unit test закрепляет это поведение. Секреты и URL с учётными данными в этот план не копируются.
- Web UI загрузился и показал форму входа. Доступ к защищённым API и проверка live/recorded video через авторизованные экраны не выполнены: валидная пользовательская учётная запись для UI не предоставлена.

- Проверен init-failure путь `processor_item`: process worker теперь публикует
  явную ошибку в runtime output envelope, когда фабрика или `create_state` падает
  до начала обработки. Thread/process регрессии находятся в
  `tests/unit/core/test_plugin_registry.py`; весь тестовый файл прошёл, после него
  не осталось `pytest`, `resource_tracker` или `spawn_main` процессов.

- Для item-модулей добавлен `IModelClassMappingProvider` с обязательной capability
  `model_class_mapping`: адаптер собирает таблицу классов из thread worker или
  передаёт metadata envelope из spawn worker. Controller принимает позднюю таблицу
  в `ClassManager` и visualizer; незадекларированный provider или неверная таблица
  даёт явную ошибку. Контракт адаптера и controller покрыт unit-тестами.
- Для generic source в `process`-режиме конфигурация проверяется на сериализуемость
  до запуска, а каждый кадр идёт через явный pickle envelope. Невозможно
  сериализовать конфигурацию — запуск отклоняется с `PluginError`; ошибка
  сериализации результата worker попадает в degraded status. Проверки находятся в
  `tests/unit/core/test_plugin_registry.py` и
  `tests/unit/capture/test_plugin_capture_source_adapter.py`; оба файла прошли,
  orphan multiprocessing workers после прогона не остались.

## Условие завершения миграции

Миграция завершена, когда встроенный inventory целиком работает через Plugin SPI, legacy protocol count равен нулю (кроме явно принятого исключения), builtin и внешний пакет проходят одинаковые контрактные тесты, полный доступный suite завершается без оставшихся процессов, штатные видео и тревоги проходят end-to-end, а внешние ограничения камер и Web UI закрыты корректной конфигурацией доступа.
