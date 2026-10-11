# План завершения миграции расширяемых модулей EvilEye

## Цель и направление

Довести встроенные компоненты и пайплайны до одного публичного Plugin SPI. Встроенные реализации остаются в репозитории и становятся контрольными примерами для внешних пакетов. `PipelineSurveillance` остаётся специализированным, но расширяемым пайплайном; `PipelineDeclarative` — простым последовательным пайплайном. В первой версии не вводить универсальный DAG, hot-plug и автоматическую установку зависимостей в работающем процессе.

Работы вести на серверной ветке `plugin_support`; каждый проверенный этап фиксировать отдельным коммитом. Пользовательские неотслеживаемые файлы не включать. До фиксации миграции этап должен иметь контрактные тесты, диагностику ошибок, запуск штатных конфигураций и подтверждённую остановку процессов.

## Текущее состояние кодовой базы

### Уже реализовано

- `evileye/core/plugins.py` содержит `PluginSpec`, `ModuleSpec`, `PipelineSpec`, `PluginRegistry` и загрузчик entry points группы `evileye.plugins`; есть проверка API version, фабрик, видов модулей, режимов и идентификаторов.
- Встроенные классы регистрируются через `register_module`; старый `EvilEyeBase.register` остаётся совместимым фасадом. Параллельный `EvilEyeBase._registry` удалён.
- `event_registry` использует общий `PluginRegistry`; встроенные и внешние event detectors создаются через `EventDetectorContext` и `EventDetectorModuleAdapter`, который владеет их конфигурацией и lifecycle. Сейчас adapter поддерживает только `thread`.
- Инвентарь закреплён тестом: 18 публичных config IDs (17 manifest modules и alias `ObjectDetectorYoloMp`); inventory test фиксирует нулевое число встроенных `legacy_*_protocol`.
- `PipelineSurveillance` принимает `modules.<group>.mode=extend|replace`, валидирует группы и виды модулей, а `ProcessorFrame` отправляет кадр каждому совместимому процессору. `module_id` принимается наряду со старым `type`.
- `PreprocessingPipeline` и `RoiFeeder` используют `processor_item` runtime.
- `parallel_items` включает общий ordered worker runtime: thread/process worker-ы получают изолированное состояние, runtime отдаёт результаты в порядке входа и помечает ошибки worker-ов как degraded. Для YOLO сохраняется старый `num_detection_threads` через перевод на `worker_count`.
- Для пользовательских тревог есть `AlarmEvent`: event detector проходит через controller в JSON и PostgreSQL adapters и в общий формат журнала. Проверены стабильный ID, идемпотентная повторная запись, retry временной ошибки, полный drain принятых batch-ей при штатной остановке, повторный start, отказ новых событий при shutdown, timeout worker-а и диагностика отказов/переполнения.
- Порядок штатного завершения API приведён к остановке ConfigRunManager и PipelineManager до закрытия Unix frame relay. Добавлена регрессия на порядок остановки.
- Исправлены выявленные тестами дефекты: проверка `track_id` с ключом `(source_id, track_id)`, синхронизация health process capture, обход нестабильной индексации Ultralytics Boxes в smoke test, ожидание асинхронного результата BoT-SORT и обнаружение записей в нескольких уровнях каталогов.

### Что пока остаётся legacy или отдельной реализацией

- `VideoCaptureOpencv` и `VideoCaptureGStreamer` реализуют общий source SPI `open/read/close`; их thread/process режимы делегируются capture backend-ам с shared-frame transport. Встроенный inventory больше не содержит `legacy_source_protocol`.
- `ObjectMultiCameraTracking` переведён на `kind="batch_processor"` и публичный `IBatchProcessor.process_batch(batch, state)`. Общий адаптер создаёт модуль и вызывает batch-контракт; исполнение пока только потоковое.
- Event detectors регистрируются через общий `PluginRegistry` и создаются runtime-адаптером с единым контекстом зависимостей. `EventsService` пока управляет подписками на источники/`ObjectsHandler`, контроллером и запуском; process-runtime для event detectors ещё не реализован.
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
5. [готово] `ModuleSpec.default_execution_mode` фиксирует режим по умолчанию; registry отвергает неподдерживаемое значение, а item/legacy/source adapters применяют заявленный режим.
6. [готово] Ограниченная очередь `processor_item` для `Frame` и пары `(data, Frame)` вытесняет самый старый ожидающий кадр, публикуя `input_queue_dropped` и `degraded`; некадровый payload при переполнении отклоняется с `input_queue_rejected`. Ordered parallel runtime пропускает sequence вытесненного кадра. Очередь EventsProcessor и DB alarm adapters сообщают об отказе/переполнении, а запись повторяется и отражается в degraded status.

**Проверки:** контрактные тесты создания, старта, остановки, ошибки init, исключения `process_item`, переполнения очереди, сериализации, отказа неподдерживаемого execution mode и schema errors.

### Этап B. Удалить legacy processor adapter по семействам

1. [готово] ObjectDetectorYolo переведён на processor_item: вход Frame/DTO, worker-local модель, ROI и class filtering, DetectionResultList; thread и spawn-process используют общий runtime. ObjectDetectorYoloMp сохраняется как alias. num_detection_threads отображается на worker_count и ordered worker pool возвращает результаты в порядке входа. При нескольких worker-ах vid_stride > 1 отклоняется, так как stride-счётчик локален worker-у. RT-DETR также переведён на item runtime; RF-DETR также использует item runtime и передаёт native Supervision detections без Ultralytics-совместимого преобразования.
2. [готово] BoT-SORT использует item runtime и хранит отдельный tracker на source_id; уменьшение frame_id сбрасывает состояние при rewind/loop. Capture публикует persistent disconnect/reconnect counters и помещает connection_generation в каждый кадр. BoT-SORT сбрасывает per-source состояние при смене поколения (включая process capture). Тест движущегося объекта подтверждает непрерывность track_id в thread и spawn process.
3. [готово] AttributeDetector и AttributeClassifier используют item runtime.
   AttributeDetector сохраняет per-class thresholds и ROI; AttributeClassifier
   обогащает tracker result по track_id. Оба модуля разрешают имена атрибутов
   по checkpoint metadata, а для псевдонимов требуют явный class_mapping.
   Thread/process и реальные модели проверены smoke-тестами. Для обоих модулей
   добавлены opt-in golden parity тесты против прежнего поведения: совпадают
   class IDs, bbox и confidence на фиксированных реальных входах.
4. После каждой группы убрать `legacy_processor_protocol` у соответствующих manifests, не удаляя compatibility `type` aliases.
5. [частично] Для YOLO, RT-DETR, AttributeDetector и AttributeClassifier добавлены opt-in golden parity tests против legacy thread реализаций на фиксированных реальных входах; классы, bbox и confidence совпадают. Проверка RT-DETR выявила и устранила регрессию округления/clip координат. Оба attribute-модуля теперь разрешают ID из checkpoint labels и требуют явный mapping для псевдонимов. BoT-SORT parity теперь закреплён отдельным golden-тестом; остаются тесты DTO/order для модулей, где их поведение отличается от inference.

**Критерий:** ни один штатный детектор, tracker или attribute module не требует `LegacyProcessorModuleAdapter`; thread/process режимы проходят один набор контрактных сценариев.

### Этап C. Мигрировать источники без потери capture-функций

1. [частично] `VideoCaptureBase` предоставляет общий `open/read/close`; контракт `Frame` документирует HxWx3 BGR `uint8`, source/frame ID, wall-clock timestamp, optional PTS, file position и connection generation. Descriptor IPC round-trip, внешний source lifecycle в thread/process и реальный GStreamer MP4 payload/PTS проверены; остаются RTSP и camera reconnect сценарии.
2. [готово] OpenCV и GStreamer подключены к source SPI через `SourceModuleAdapter`. Их codec handling, reconnect, split/crop, запись сегментов, ограниченные очереди и shared-frame capture остаются в специализированных backend-ах.
3. [частично] Для встроенных capture backend-ов режим `thread/process` исполняется их собственным backend-ом; сторонние source plugins используют общий thread/spawn runtime. `SourceModuleAdapter` публикует capture health и worker status. Тесты закрепляют ровно один `open/close` при EOF, process shutdown и то, что зависший thread не скрывается и не может быть перезапущен поверх живого worker-а; blocking process завершается с явной degraded-диагностикой. В process-режиме parent proxy отдельно публикует наблюдаемые переходы доступности кадров и `backend_connection_generation`, который приходит в metadata кадра от дочернего backend-а и фиксирует быстрые reconnect без паузы кадров.
4. [частично] Остановка проверена в thread/process тестах и полном unit suite без оставшихся worker-ов. Проверки RTSP/GStreamer зависят от доступности backend-а и камеры.

**Проверки:** видеофайл, loop/reconnect, синтетический RTSP и доступные реальные камеры; запись и ffprobe; проверка отсутствия worker, сокетов и очередей после stop.

### Этап D. Завершить batch и event/alarm lifecycle

1. [готово] `ObjectMultiCameraTracking` использует batch SPI с явной синхронизацией и ограничением `thread`-режима; контракт покрыт unit-тестами.
2. [готово для thread] Фабрики и lifecycle Event detectors используют `PluginRegistry`, `EventDetectorContext` и общий runtime-адаптер; `EventsService` остался управляющим слоем зависимостей, запуска и освобождения ресурсов. Event detectors пока не поддерживают process execution.
3. [готово для JSON и PostgreSQL] `AlarmEvent` проходит от стороннего detector-а через контроллер, оба persistence adapter-а и модель журнала. PostgreSQL integration test проверяет реальную запись, уникальность по `alarm_id` и удаляет тестовую запись; unit test проверяет параметры и retry. Формирование строки общего формата журнала проверяет unit test; авторизованный live экран Web UI не проверен.
4. [частично] Ошибка detector-а не останавливает соседние правила; очередь DB adapter-а ограничена, worker повторяет временные ошибки. `EventsProcessor.stop()` закрывает приём новых batch-ей и дренирует уже принятые; чистый restart создаёт новый worker. Timeout и наличие живого worker-а/ожидающих batch-ей публикуются в runtime stats, постоянный отказ адаптера и переполнение очереди выставляют degraded с причиной. Проверка длительного отказа PostgreSQL, восстановления под нагрузкой и долговечный outbox остаются.

**Критерий:** внешний event/alarm detector не меняет ядро для нового события и проходит до выбранного хранилища и общего представления в журнале; режим исполнения и отказ detector-а диагностируются явно.

### Этап E. Свести пайплайны к реестру и проверить внешний пакет

1. [готово] `PipelineSurveillance`, `PipelineCapture` и `PipelineDeclarative` зарегистрированы как builtin `PipelineSpec`; `PipelineService` разрешает их через PluginRegistry.
2. [готово] `pipeline_class` сохранён как compatibility alias; неизвестный выбранный pipeline приводит к диагностируемой ошибке без fallback.
3. [готово] Оставить `PipelineSurveillance` фиксированным графом стадий; порядок, правила `extend`/`replace`, несколько детекторов на один источник и ограничения thread-only стадий описаны в `PLUGINS.md` и `PIPELINE_ARCHITECTURE.md`.
4. [готово] Минимальный внешний пакет установлен editable-режимом в изолированное server-side virtualenv; entry point `evileye.plugins` обнаружен, модуль зарегистрирован без изменения/переустановки EvilEye. В example package указан build backend с PEP 660 поддержкой.
5. [готово] Контрактные тесты покрывают конфликт ID, неизвестный module/pipeline, неверную API version, общую ошибку импорта, отсутствующую зависимость с указанием entry point и имени пакета, неверный IPipeline и отказ без fallback.

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
- `tests/unit` после source health, frame connection generation и BoT-SORT reset завершился на 100%; после прогона фоновых `pytest`, `resource_tracker`, `spawn_main`, `MpWorkerCapture` и `PluginSource` процессов не осталось. OpenCV loop integration на spawn capture подтвердил передачу connection generation в кадре и runtime health.
- Невалидный сторонний `PipelineSpec` проверяется отдельно: `PipelineService` сообщает об отсутствии методов `IPipeline` и не подставляет встроенный pipeline. Тест вместе с registry и custom-pipeline тестами прошёл.

- Проверен init-failure путь `processor_item`: process worker теперь публикует
  явную ошибку в runtime output envelope, когда фабрика или `create_state` падает
  до начала обработки. Thread/process регрессии находятся в
  `tests/unit/core/test_plugin_registry.py`; весь тестовый файл прошёл, после него
  не осталось `pytest`, `resource_tracker` или `spawn_main` процессов.

- AttributeDetector переведён с собственного `DetectionThreadBase` lifecycle на `processor_item`: вход `Frame` выдаёт `DetectionResultList`, class mapping передаётся через runtime metadata, модели и ROI обрабатываются внутри выбранного worker. Legacy-протокол и его специализированные потоки больше не используются этим модулем; thread/process поведение и реальная `y8mhardhats.pt` inference в spawn worker проверены. `vid_stride` выдаёт пустой результат для пропущенных кадров, а `num_detection_threads != 1` отклоняется явно.
- AttributeClassifier переведён на `processor_item`: конфигурация и модель создаются в worker, ROI берутся из `TrackingResultList.roi_data`, `attr_results` индексируются по `track_id`; process worker читает shared frame без его уничтожения. Ошибки inference теперь попадают в runtime diagnostics. Дополнительно пройден opt-in integration smoke с реальной `yolo11n.pt`: spawn worker обработал ROI из shared-frame handle, вернул атрибут по `track_id` и сохранил handle; сценарий закреплён в `tests/integration/attributes/test_attribute_modules_process.py`.
- ObjectDetectorRfdetr переведён на processor_item с отдельным RF-DETR runtime. Поддержаны nano/small/medium/large, native Supervision result, class filtering и ROI mapping и num_detection_threads через ordered worker_count pool; неизвестная модель и некорректная batch cardinality вызывают явную ошибку. Реальная модель не smoke-тестировалась: локальных RF-DETR весов нет.
- ObjectDetectorRtdetr переведён на общий processor_item контракт: RT-DETR создаётся внутри worker через Ultralytics runtime, model mapping и ROI проходят тем же путём. Проверены fake-runtime unit test и opt-in spawn smoke с реальной моделью rtdetr-l.pt при imgsz=640.
- ObjectDetectorYolo переведён на `processor_item`: модель и runtime создаются внутри каждого worker, результаты ROI переводятся в координаты кадра, используется единый `DetectionResultList`. Ordered item runtime поддерживает несколько worker-ов в thread/process и сохраняет порядок выхода. Старый `num_detection_threads` отображается на `worker_count`; `ObjectDetectorYoloMp` оставлен как alias. Реальная `yolo11n.pt` обработка в двух spawn worker-ах добавлена в opt-in smoke `tests/integration/attributes/test_attribute_modules_process.py` и прошла. Полный `tests/unit` после миграции прошёл до 100%.
- BoT-SORT переведён на `processor_item`: thread и spawn process используют один контракт, runtime state изолирован по `source_id`, shared-frame handle читается без уничтожения. Unit-проверки подтверждают per-source state, reset на rewind, пустые результаты в thread/process и сериализацию реального tracking result в spawn worker. Pipeline загружает encoder только для legacy thread tracker; item worker создаёт его у себя. Полный `tests/unit` после миграции завершился с `exit=0` и дошёл до 100%; после прогона не осталось `pytest`, `resource_tracker` или `spawn_main` процессов.
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

- После lifecycle-изменений полный `tests/unit` завершился с `exit=0`; точечные проверки остановки DB workers при недоступном соединении и отложенного старта event adapters прошли. Новый полный integration-прогон собрал 358 тестов, но за 360 секунд дошёл только до 40% и был остановлен timeout; это не даёт основания считать integration suite успешным. После остановки не осталось процессов этого прогона.

- После уточнения ошибок загрузки `PluginManager` отдельно помечает `ModuleNotFoundError` как отсутствующую зависимость и сообщает её имя вместе с entry point; registry, controller lifecycle и adapter tests прошли. Целевые integration-проверки database controller без БД и PostgreSQL alarm persistence завершились: 8 passed; оставшихся pytest/multiprocessing процессов нет.

- Очереди `processor_item` получили типизированную backpressure-политику: вытесненные кадры учитываются в runtime stats, а non-frame payload сохраняет явный reject. Thread, process-queue helper и ordered parallel tests прошли; полный `tests/unit` завершился с `exit=0`, после него не осталось pytest, resource_tracker, spawn_main или MpWorker процессов. Alarm overflow/retry tests остаются зелёными.

## Порядок оставшихся работ на 2026-10-11

Первая версия плана **не завершена**. Registry/SPI, встроенные item модули,
основные конфигурационные режимы и внешний пакет уже работают; оставшиеся
пункты ниже закрывают проверяемые пробелы миграции и эксплуатации.

### 1. Закрыть parity tracker-ов и DTO

- AttributeClassifier уже сравнен с legacy реализацией на фиксированном ROI:
  class mapping, confidence, результат по track_id и bbox закреплены golden
  test-ом.
- [готово] Для BoT-SORT добавлена воспроизводимая синтетическая последовательность с движением, пропусками detections и восстановлением track_id. Golden bbox и ID сняты со старого thread worker на `27fcb2a`; SPI thread и spawn-process совпадают с ними. Reset после rewind/reconnect проверяется отдельными контрактными тестами.
- Зафиксировать, какие новые поля DTO намеренно добавлены, чтобы parity проверяла
  семантику, а не сравнение сериализаций побайтно.

**Готово, когда:** tracker имеет воспроизводимый golden test против предыдущего
поведения и одинаковые результаты через SPI thread/process там, где оба режима
заявлены; порядок и DTO проверяются отдельными контрактами.

### 2. Закрыть source lifecycle и end-to-end конечную видеозапись

- [частично] Согласовать документированную модель кадра: размеры/цветовой формат, timestamp, sequence, connection generation и владение shared-frame handle; descriptor round-trip и внешний `open/read/close` source проверяются в thread/process. GStreamer MP4 integration test проверяет BGR payload, уникальные frame IDs, сохранение PTS при копировании и новый connection generation при file-loop EOS. Остаются RTSP transport/backend и reconnect тесты на реальных камерах.
- [готово] Полный `PipelineSurveillance` finite-video test считает уникальные frame IDs на source/detector/tracker stage и проверяет равенство множеств без повторной выдачи последнего кадра. Записанный сегмент читается `ffprobe`; detector/tracker проверены в thread и spawn-process после дедупликации source SPI.
- [частично] Добавить deterministic file-loop/reconnect сценарии для встроенного capture. GStreamer local MP4 loop теперь проверяет новый connection generation и уникальные frame IDs; остаются RTSP transport и reconnect проверки на камерах.
  Синтетический RTSP прогонять независимо от доступности реальных камер; реальные
  RTSP результаты фиксировать отдельно для каждого backend и transport.

**Готово, когда:** finite-video прогон доказывает прохождение кадров по стадиям и
корректное освобождение ресурсов в thread/process режимах.

### 3. Зафиксировать границу event/alarm runtime

- Нагрузочно проверить ограниченную очередь и повтор записи при временно
  недоступной БД: очередь не растёт без границ, восстановление сохраняет порядок
  допустимых повторов, `alarm_id` исключает дубликаты, stop дренирует очередь.
- Проверить, что падение одного event detector не останавливает соседние правила,
  а adapter и pipeline остаются `degraded` до успешного восстановления.
- Для event detectors оставить явную проверку отказа `process`-режима. Отдельно
  решить, требуется ли им spawn runtime: текущие зависимости на `ObjectsHandler`
  и контроллер не являются сериализуемым контрактом, поэтому расширять режим без
  отдельного протокола доставки событий нельзя.

**Готово, когда:** отказ/восстановление БД и detector-а наблюдаемы, а ограничение
по process режиму документировано и проверено контрактным тестом.

### 4. Закрыть regression и эксплуатационные проверки

- Разобрать зависание завершения полного integration suite после pytest summary;
  установить владельцев оставшихся потоков/worker-ов и обеспечить штатное закрытие.
  Не считать suite зелёным только по summary, пока процесс не завершился с кодом 0.
- Последовательно прогнать полный unit и integration наборы, затем штатный
  finite-video smoke и plugin-package smoke; после каждого проверить процессы.
- Проверить Web UI и защищённые API с валидной учётной записью, если она доступна;
  без неё оставить эту проверку открытым внешним блокером, не подменяя авторизацию.
- В финале снять inventory всех builtin modules и capabilities; завершать миграцию
  только при нуле `legacy_processor_protocol`/`legacy_source_protocol`, а
  thread-only исключения оставить явно в документации.

**Готово, когда:** каждый прогон имеет exit code, подтверждённый shutdown, а
внешние ограничения отделены от дефектов репозитория.

### Актуальная проверка 2026-10-11

- Сравнение с прежним `AttributeDetectionThread` на `yolo11n.pt` и фиксированном
  `bus.jpg` выявило ошибку: без `class_mapping` атрибут `bottle` получал ID 1
  вместо ID 39. `AttributeDetector` теперь использует имена классов checkpoint;
  если запрошенной метки нет, требует явный `class_mapping`. Реальный smoke
  подтвердил `{person: 0, bottle: 39}`.
- AttributeClassifier очищен от параллельного legacy lifecycle: модуль больше не
  наследует EvilEyeBase и не содержит собственных put/get очередей, MP worker и
  dispatch thread. Его запуск/stop выполняет только ItemModuleAdapter; тест
  закрепляет отсутствие старого ProcessorFrame интерфейса.
- Добавлен opt-in golden test
  tests/integration/attributes/test_attribute_classifier_legacy_parity.py;
  реальный yolo11n.pt spawn smoke проходит через новый mapping по checkpoint.
- Добавлен opt-in golden test
  `tests/integration/attributes/test_attribute_detector_legacy_parity.py`.
  Он сравнивает class IDs, bbox и confidence с результатом legacy реализации;
  новый SPI дополнительно сохраняет имя атрибута в detection metadata.
- Контрактные тесты для metadata mapping и обязательного явного mapping при
  незнакомых labels прошли. Команда `EVILEYE_RUN_MODEL_PARITY=1 pytest -q
  tests/unit/attributes/test_attribute_detector_plugin_runtime.py
  tests/integration/attributes/test_attribute_detector_legacy_parity.py`
  завершилась успешно.
- Первый полный unit прогон обнаружил устаревшую RT-DETR fake-фикстуру без
  `orig_img`. Фикстура дополнена исходным ROI-изображением без ослабления проверки
  clipping. Повторный `QT_QPA_PLATFORM=offscreen pytest -q tests/unit` дошёл до
  100% с exit code 0; тестовых `pytest`, `resource_tracker`, `spawn_main`,
  `PluginSource` и `MpWorkerCapture` процессов после прогона не осталось.
- После удаления второго lifecycle AttributeClassifier и перехода обоих
  attribute-модулей на общий mapping resolver полный `QT_QPA_PLATFORM=offscreen
  pytest -q tests/unit` повторно завершился с exit code 0 и дошёл до 100%;
  orphan worker-процессов после прогона не осталось.
- Полный integration suite, RTSP backend-проверки и авторизованный просмотр Web UI остаются открытыми. AttributeClassifier parity и process smoke
  добавлены и проходят; общая миграция не завершена.

## Условие завершения миграции

Миграция завершена, когда встроенный inventory целиком работает через Plugin SPI, legacy protocol count равен нулю (кроме явно принятого исключения), builtin и внешний пакет проходят одинаковые контрактные тесты, полный доступный suite завершается без оставшихся процессов, штатные видео и тревоги проходят end-to-end, а внешние ограничения камер и Web UI закрыты корректной конфигурацией доступа.
- На сервере после фиксации bbox parity: весь tests/unit завершился с exit=0; интеграционные группы pipeline, registry и CLI working-directory/minimal-no-DB завершились с exit=0 (21 тест). Совместные opt-in golden проверки YOLO и RT-DETR прошли; после проверок фоновых pytest и multiprocessing worker-ов не осталось.
- BoT-SORT: `tests/unit/object_tracker/test_botsort_plugin_runtime.py::test_botsort_matches_legacy_frame_sequence_golden` проверяет 8 кадров с потерянными detections, восстановлением track_id и bbox относительно legacy worker; thread и spawn-process варианты прошли.

- PipelineSurveillance finite-video E2E: `tests/integration/pipeline/test_pipeline_surveillance_video_e2e.py` прогоняет 20 кадров через встроенный OpenCV capture, YOLO и BoT-SORT. Счётчики stage outputs сравнивают frame IDs, output recording проверяется `ffprobe`; thread и spawn-process варианты прошли (2 passed), degraded=false, после shutdown worker-ов нет. Запуск opt-in через `EVILEYE_RUN_SURVEILLANCE_VIDEO_E2E=1`.

- Source contract: `Frame` получил API docstring; `docs/PLUGINS.md` описывает payload и ownership shared-memory handle. `test_capture_descriptor_payload` закрепляет передачу frame metadata при decode descriptor. Source health, frame PTS и descriptor IPC unit tests прошли (6 passed).

### Продолжение 2026-10-11: отказ и восстановление alarm storage

- [готово] Добавлена нагрузочная регрессия DB alarm adapter: при отказе БД
  адаптер исчерпывает три попытки записи, после чего следующий запрос отражает
  восстановление; две уже принятые записи сохраняются в FIFO-порядке. При
  заполнении очереди третья запись отклоняется явно. Проверяются ограничение
  очереди, число попыток, сохранённые `alarm_id`, пустая очередь после stop и
  `degraded` с причиной потери первой тревоги. Это подтверждает наблюдаемость, но
  не гарантирует сохранение события после исчерпания retries: durable outbox
  по-прежнему вне версии 1.
- [готово] DB adapter теперь сериализует приём `insert/update` с `stop`, чтобы
  событие либо принято до закрытия и дренировано, либо явно отклонено. Остановка
  worker ограничена `stop_timeout_secs`; timeout оставляет `worker_alive=true`,
  `closing=true`, увеличивает `shutdown_timeouts` и запрещает перезапуск до
  фактического выхода старого потока. После выхода допустим безопасный restart.
  Синхронные JSON adapters используют тот же acceptance boundary.
- [готово] Runtime stats разделяют `enqueue_rejections` и
  `terminal_write_failures`; старый `queue_failures` сохранён как агрегированный
  счётчик для совместимости. Регрессия подтверждает: одна окончательно
  несохранённая тревога и одно переполнение дают по одному в соответствующих
  счётчиках.
- [готово] Полный `QT_QPA_PLATFORM=offscreen python3.10 -m pytest -q tests/unit`
  завершился с exit code 0. Первый прогон поймал две фикстуры capture SPI,
  возвращавшие dict вместо `Frame`; обе фикстуры приведены к публичному Frame
  контракту, затем полный прогон прошёл. После него фоновых pytest и
  multiprocessing worker процессов не обнаружено.
- Целевые alarm/JSON проверки завершились успешно; DB adapter
  lifecycle/outage regression включена в этот прогон. Осталось только
  предупреждение обновления установленной Albumentations.

## Дальнейший порядок работ

Первая версия плана **всё ещё не завершена**. Следующий приоритет — закрыть
проверяемые границы версии 1; только после этого имеет смысл отдельно принимать
решение о DAG, hot-plug и долговечной очереди.

1. **Закрыть runtime тревог.** Счётчики отказа приёма и terminal write уже
   разделены, `queue_failures` сохранён как совместимый агрегат. Осталось
   проверить переход соединения PostgreSQL down/up в отдельном контролируемом
   integration fixture и повтор с тем же `alarm_id`; текущая integration
   проверяет реальную идемпотентную запись в доступную БД, а длительный outage
   пока моделируется unit fake-ом. Проверить, что runtime/API показывает latched
   degraded после окончательной потери. Уточнить границу shutdown: `stop()` теперь
   ограничивает join и сообщает о живом worker-е, но не может прервать блокирующий
   вызов драйвера; в `DatabaseControllerPg` сейчас нет явных connect/statement
   deadlines. Добавить и проверить конечные libpq/SQL timeouts либо безопасную
   отмену запроса, чтобы worker действительно завершался. Не добавлять
   event-detector `process` режим без сериализуемого контракта доставки объектов
   и событий.
2. **Закрыть source transport.** Добавить независимый локальный RTSP fixture
   (предпочтительно проектный test dependency или воспроизводимый контейнерный
   сервис, без скачивания бинарника во время теста); проверять DESCRIBE/SETUP/PLAY,
   таймаут, EOF/reconnect и смену `connection_generation` отдельно для OpenCV и
   GStreamer. Затем повторить реальные камеры и записать результат по каждой
   камере/backend/transport. Текущий блокер: локальный RTSP server fixture на
   сервере отсутствует; камеры `.199`/`.202` возвращают `RTSP 250` на PLAY в
   GStreamer.
3. **Закрыть полный integration shutdown.** Разбить suite на независимые группы,
   для каждой сохранять exit code и список живых потоков/процессов; найти владельца
   ресурсов, из-за которых общий прогон зависал после summary. После фикса пройти
   полный набор с конечным timeout и получить exit code 0, затем повторить
   finite-video, внешний editable package и проверить отсутствие worker-ов.
4. **Закрыть эксплуатационную часть.** На действующих конфигурациях отдельно
   подтвердить конечную видеозапись с детекцией/трекингом и камеру через каждый
   поддержанный backend. Проверку защищённых UI экранов выполнить только с
   валидной учётной записью; без неё оставить конкретный внешний блокер.
5. **Завершить inventory миграции.** Снять список всех builtin module IDs,
   capabilities и execution modes; для каждого оставить тест thread/process,
   golden parity или явное thread-only обоснование. Нулевой legacy protocol count
   и успешный shutdown обязательны для завершения v1.

После закрытия этих пунктов отдельно подготовить RFC для следующей версии:

- нужен ли граф/DAG пайплайна сверх `PipelineDeclarative` и
  специализированного `PipelineSurveillance`;
- нужен ли durable outbox/повтор доставки тревог через перезапуск;
- требования к доверенной установке сторонних пакетов, lock-файлам,
  совместимости версий и диагностике конфликтов;
- нужен ли управляемый runtime reload плагинов; он не должен означать
  автоматическую установку зависимостей;
- какие интерфейсы и capability manifest должны стабилизироваться как публичный
  SDK, включая миграционную политику.


### PostgreSQL deadlines для shutdown

- [готово] `DatabaseControllerPg` поддерживает `connect_timeout_secs` (по
  умолчанию 5 секунд) и `statement_timeout_ms` (30 секунд); параметры передаются
  и основному pool, и admin connection для создания БД. Для соединений включены
  TCP keepalive с заданными интервалом и числом проб. Значения доступны через
  `set_params/get_params`, проверены unit-тестом параметров pool и реальным
  integration-запросом `SHOW statement_timeout` плюс контролируемым `pg_sleep`,
  который завершается `QueryCanceled` в пределах заданного deadline.
- [готово] Alarm adapter использует `DatabaseControllerPg.query_once`; поэтому
  для очередной тревоги есть один владелец retries (три попытки worker-а), а
  прямой `query_checked` сохраняет собственный bounded retry. PostgreSQL
  integration test подменяет запись на `pg_sleep` и проверяет, что statement
  timeout даёт один terminal failure, после чего worker завершается в пределах
  stop budget. Нужно отдельно инвентаризировать другие DB adapters на вложенные
  retries и подобрать production shutdown budget к лимитам конфигурации.


### Продолжение 2026-10-11: единый retry-контур PostgreSQL adapters

- [готово] `AttributeEvents`, `CamEvents`, `FieldOfViewEvents`, `Objects`,
  `SystemEvents` и `ZoneEvents` переведены с `query()` на `query_once()`. Теперь
  исключение соединения доходит до общего bounded retry worker-а; успешный
  возврат `None` из совместимого `query()` больше не маскирует отказ записи.
  Повторная SQL-попытка принадлежит одному worker-у, без вложенного
  `query_checked` retry.
- [готово] `ZoneEvents` больше не переопределяет цикл очереди: bounded retry,
  shutdown drain и terminal failure stats выполняются `DatabaseAdapterBase`.
- [готово] Ошибки сохранения изображений и некорректные `RETURNING` строки
  после успешного SQL commit отражаются как terminal storage failure и не
  запускают повторный INSERT. Уже сохранённая object/zone запись уведомляется
  даже при повреждённом результате или отсутствии опционального кадра.
- [готово] Добавлены контрактные тесты на все шесть адаптеров: три попытки,
  terminal failure, нулевой processed count и общий worker для ZoneEvents.
  Также проверены отсутствие повтора INSERT при ошибке записи изображения и
  уведомление о zone event без изображения.
- Полный `QT_QPA_PLATFORM=offscreen python3.10 -m pytest -q tests/unit`
  повторно завершился с exit code 0 после malformed `RETURNING` regressions;
  после прогона нет pytest и multiprocessing worker-ов.

**Следующий приоритет:** источник-ориентированный RTSP fixture и полный
integration shutdown. На сервере доступны GStreamer 1.20.3, `gst-launch-1.0`,
H.264 encoder/payloader plugins, но нет GI namespace `GstRtspServer`; текущие
RTSP integration tests используют реальные камеры и пароль из environment, а
изолированный локальный RTSP fixture отсутствует. Не выполнять system package
installation из тестов; подобрать воспроизводимую test dependency или проверяемый
контейнерный fixture. Полный integration shutdown остаётся отдельным открытым
пунктом.
