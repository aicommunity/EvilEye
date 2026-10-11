# План завершения миграции расширяемых модулей EvilEye

## Цель и направление

Довести встроенные компоненты и пайплайны до одного публичного Plugin SPI. Встроенные реализации остаются в репозитории и становятся контрольными примерами для внешних пакетов. `PipelineSurveillance` остаётся специализированным, но расширяемым пайплайном; `PipelineDeclarative` — простым последовательным пайплайном. В первой версии не вводить универсальный DAG, hot-plug и автоматическую установку зависимостей в работающем процессе.

Работы вести на серверной ветке `plugin_support`; каждый проверенный этап фиксировать отдельным коммитом. Пользовательские неотслеживаемые файлы не включать. До фиксации миграции этап должен иметь контрактные тесты, диагностику ошибок, запуск штатных конфигураций и подтверждённую остановку процессов.

## Текущее состояние кодовой базы

### Уже реализовано

- `evileye/core/plugins.py` содержит `PluginSpec`, `ModuleSpec`, `PipelineSpec`, `PluginRegistry` и загрузчик entry points группы `evileye.plugins`; есть проверка API version, фабрик, видов модулей, режимов и идентификаторов.
- Встроенные классы регистрируются через `register_module`; старый `EvilEyeBase.register` остаётся совместимым фасадом. Параллельный `EvilEyeBase._registry` удалён.
- `event_registry` использует общий `PluginRegistry`; legacy event detectors создаются через `EventDetectorContext` и `EventDetectorModuleAdapter`. Для process-модулей доступны `event_updates` от объектов, ограниченные JPEG-вложения `event_frames`, `source_updates` от источников и `event_commands` от контроллера. Встроенные `SystemEventsDetector`, `CamEventsDetector`, `ScheduleAlarmEventsDetector`, `AttributeEventsDetector` и `ZoneEventsDetector` работают через process runtime. Zone получает сериализуемые object snapshots и ограниченные JPEG-вложения; команды изменения зон идут через `event_commands`.
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
- Event detectors регистрируются через общий `PluginRegistry` и создаются runtime-адаптером с единым контекстом зависимостей. `EventsService` управляет подписками и запуском; process runtime передаёт object snapshots, source transitions, команды контроллера и ограниченные JPEG-вложения через `EventUpdate`. Все встроенные event detectors работают в process режиме.
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

- [частично] Согласовать документированную модель кадра: размеры/цветовой формат, timestamp, sequence, connection generation и владение shared-frame handle; descriptor round-trip и внешний `open/read/close` source проверяются в thread/process. GStreamer MP4 integration test проверяет BGR payload, уникальные frame IDs, сохранение PTS при копировании и новый connection generation при file-loop EOS. Остаются failure/reconnect тесты для поддерживаемых transport/backend вариантов; live кадр и запись уже проверены на двух камерах.
- [готово] Полный `PipelineSurveillance` finite-video test считает уникальные frame IDs на source/detector/tracker stage и проверяет равенство множеств без повторной выдачи последнего кадра. Записанный сегмент читается `ffprobe`; detector/tracker проверены в thread и spawn-process после дедупликации source SPI.
- [частично] Добавить deterministic file-loop/reconnect сценарии для встроенного capture. GStreamer local MP4 loop теперь проверяет новый connection generation и уникальные frame IDs; остаются RTSP failure/reconnect проверки на камерах.
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
- Полный integration suite, локальный RTSP fixture/reconnect и авторизованный просмотр Web UI остаются открытыми. Live RTSP кадр и запись проверены; AttributeClassifier parity и process smoke
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

1. **Закрыть runtime тревог.**
   - [готово] Счётчики enqueue rejection и terminal write разделены;
     `queue_failures` сохранён как совместимый агрегат.
   - [готово] PostgreSQL down/up проверен через локальный TCP forwarding proxy:
     сброс существующего соединения вызывает retry, восстановление forwarding
     сохраняет принятую тревогу, повтор того же `alarm_id` оставляет одну строку.
   - [готово] `query_once` удаляет сломанное соединение из пула и сохраняет
     исходный `OperationalError`, чтобы общий retry-контур мог восстановиться.
   - [готово] Ограничения `connect_timeout_secs` и `statement_timeout_ms`
     проверяются unit и PostgreSQL integration тестами.
   - [готово] `EventsProcessor.get_runtime_stats()` включает health и counters
     DB adapters; unit tests закрепляют degraded после terminal write/overflow.
     Публичный HTTP endpoint и отображение этих stats в Web UI ещё не проверены.
   - [ограничение v1] Event detectors остаются thread-only: process режим не
     добавляется без сериализуемого протокола доставки событий.
2. **Закрыть source transport.**
   - [готово] Live frame tests проходят через GStreamer и OpenCV SPI на камерах
     `.199` и `.200`; GStreamer shared recorder записал MP4 с пакетами на обеих
     камерах. OpenCV проверки используют CAP_FFMPEG.
   - [осталось] Добавить локальный воспроизводимый RTSP fixture и без реальных
     камер проверять DESCRIBE/SETUP/PLAY, timeout и reconnect для OpenCV и
     GStreamer. Текущие live smoke не заменяют детерминированный transport test.
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

### Продолжение 2026-10-11: один GStreamer recording runtime

- [готово] Удалена inline legacy recording branch из `GStreamerCaptureRecordingMixin`.
  Continuous recording подключается только через `GstContinuousRecorder`; ошибка
  setup больше не маскируется переходом к дублирующей реализации. Ошибки
  подключения recording queue и создания элементов выходят как явный отказ.
- [готово] Подключение branch стало транзакционным: частично добавленные элементы
  переводятся в NULL и удаляются из capture pipeline при ошибке link/setup.
  Cleanup и `VideoCaptureGStreamer` больше не содержат отдельного recorder
  check-thread и legacy element state.
- [готово] Recorder отслеживает поступление первого muxed buffer. При остановке
  до первого кадра он отсоединяет branch без блокирующего EOS; при наличии видео
  выполняет EOS и ждёт финализации MP4. Это также устраняет зависание decoder
  fallback на файле без H.264, когда запись была включена, а ветка ещё не получила
  ни одного кадра.
- [готово] Локальный GStreamer video-file E2E прошёл: кадры получены, branch
  подключён через общий recorder, создан MP4, `ffprobe` подтвердил video packets.
  GStreamer capture/reconnect/frame integration группа — 8 passed; полный
  `tests/unit` — exit code 0, оставшихся pytest/worker-процессов нет.
- В процессе первый E2E обнаружил, что init fallback мог блокироваться на EOS до
  первого кадра; добавлены отдельные regression tests на остановку пустой ветки
  и rollback частично подключённых GStreamer элементов.

Открытыми остаются локальный RTSP fixture (на сервере отсутствует
`GstRtspServer`) и root-cause shutdown полного integration suite. Реальные камеры
и защищённые Web UI требуют отдельной проверяемой конфигурации доступа.

### Продолжение 2026-10-11: RTSP startup и единый GStreamer teardown

- [готово] IP-camera pipeline больше не ждёт `get_state(CLOCK_TIME_NONE)` до
  запуска GLib loop: RTSP state transition асинхронен, ошибки приходят через bus,
  работоспособность подтверждается первым кадром. Для finite source оставлен
  bounded preroll с пределом 10 секунд.
- [готово] `VideoCaptureGStreamer.release()` использует общий teardown pipeline
  вместо второго списка переходов PAUSED/READY/NULL. Повторный release
  сериализован, а reconnect не запускает новый pipeline, пока предыдущий native
  teardown ещё выполняется.
- [готово] Добавлены unit tests для bounded/async state startup и единственного
  serialized teardown. Live RTSP проверки вынесены в дочерний процесс и
  редактируют credentials из stdout/stderr, чтобы native crash не завершал
  основной pytest процесс и не раскрывал пароль.
- На сервере unit tests для GStreamer startup/release/recorder прошли (11 passed),
  RTSP pipeline contract tests прошли (2 passed), локальный MP4 recorder E2E
  прошёл и `ffprobe` увидел packets.
- Реальная камера `.199`: live child завершился с `SIGSEGV` (`exit=-11`) до
  получения BGR кадра; stdout/stderr процесса пустые. Следовательно, RTSP
  camera/backend runtime всё ещё не подтверждён, а live recording test на камере
  не запускался. Наблюдение не позволяет приписать сбой только камере или
  GStreamer plugin; нужен core dump с symbols или локальный RTSP fixture для
  разделения причин.

- Повторное расследование показало, что crash камеры `.200` до исправления
  проходил через `libproxy` (`px_proxy_factory_get_proxies`) при загрузке GIO
  системного proxy resolver. Для прямых RTSP источников GStreamer теперь
  устанавливает `GIO_USE_PROXY_RESOLVER=dummy` через `setdefault` до импорта GI;
  явно заданное пользователем значение сохраняется.
- После этого изменения обе live-камеры `.199` и `.200` прошли проверки без
  ручной установки переменной: изолированный процесс получил BGR кадр, а
  shared recorder записал MP4. `ffprobe` подтвердил наличие пакетов в каждой
  записи.
- Старые наблюдения о crash обеих камер относятся к запуску до настройки
  resolver; повторные live-проверки подтверждают исправление в текущей среде.

### Продолжение 2026-10-11: RTSP source через OpenCV SPI

- [готово] Добавлен opt-in live integration test для встроенного
  `VideoCaptureOpencv` через `SourceModuleAdapter`; он проверяет получение BGR
  кадра с сохранением `source_id`. Тест запускает native capture в дочернем
  процессе, принимает учетные данные только через environment и скрывает их из
  диагностики.
- Проверка прошла для камер `.199` и `.200`; обе вернули кадр через
  `CAP_FFMPEG` без аварии worker-а.
- Локальный воспроизводимый RTSP server fixture и reconnect/transport contract
  без реальных камер остаются открытой задачей. Успешный live smoke не заменяет
  детерминированные DESCRIBE/SETUP/PLAY, timeout и reconnect проверки.


### Продолжение 2026-10-11: восстановление PostgreSQL после TCP outage

- Контролируемый сброс TCP proxy выявил, что `query_once()` возвращал закрытое
  соединение в pool; rollback на закрытом соединении маскировал сетевой
  `OperationalError` как `InterfaceError`, из-за чего retry прекращался.
- [готово] `query_once()` теперь явно завершает транзакцию, пытается rollback при
  ошибке и передаёт закрытое/неисправное соединение в `putconn(close=True)`.
  Ошибка возврата в pool не маскирует первичный сбой запроса.
- [готово] Новая PostgreSQL integration проверка включает и отключает только
  свой локальный forwarding proxy, не останавливая общую БД. После обрыва
  worker повторяет запрос, сохраняет тревогу после восстановления, а повтор с
  тем же `alarm_id` даёт одну запись.
- [готово] Добавлен unit test на случай, когда rollback выдаёт `InterfaceError`;
  он проверяет сохранение исходного `OperationalError` и удаление соединения
  из pool.
- DB unit/integration группы завершились успешно; полный `tests/unit` завершён
  с exit code 0. После прогона не осталось pytest или multiprocessing worker-ов.

### Продолжение 2026-10-11: lifecycle тестов и UI workers

- [готово] `JournalInitThread` хранится в сильном реестре до тех пор, пока
  session/per-test shutdown не подтвердит завершение `QThread`; worker
  проверяет отмену между этапами и закрывает DB connection при отмене.
  Регрессионный тест удерживает thread в `run()` и проверяет, что реестр
  очищается только после `wait()`.
- [готово] Тестовая `QApplication` fixture стала session-scoped с сильной
  ссылкой на один wrapper. Это устранило преждевременное освобождение wrapper
  между GUI-тестами. Общий обход/удаление Qt-виджетов на каждом тесте удалён:
  он сам приводил к native crash при работе с устаревшими QObject wrappers.
- [готово] Per-test и session cleanup останавливают preview/streaming services,
  `MpControl`, `ServerProcessManager`, recorder и journal init workers до конца
  тестовой сессии. `MpControl.stop()` закрывает IPC queues и join-ит feeder
  threads; server manager выполняет аналогичный cleanup.
- [готово] Тесты journal columns теперь используют private `tmp_path` fixtures,
  а не каталог `EvilEyeData` с пользовательскими/производственными записями.
  Исправлен устаревший DB fake zone adapter: он реализует `query_once()`, как
  требует production adapter.
- Проверки на сервере: полный `tests/unit` — 100%, exit code 0; целевые тесты
  сервисов, MpControl, journal lifecycle, zone DB adapter и journal UI — 25
  passed; полный `tests/integration` — 100%, exit code 0 с предусмотренным
  режимом `EVILEYE_PYTEST_FORCE_EXIT=1`.
- Остаётся ограничение окружения: обычный запуск integration доходит до 100%,
  но PyQt 6.11 получает SIGSEGV в `cleanup_on_exit()` при `Py_FinalizeEx`.
  Это подтверждено нативным backtrace под gdb; все assertions перед завершением
  проходят. Для полного набора используется существующий opt-in force-exit
  режим, который срабатывает после session fixture cleanup и сохраняет exit
  status pytest. Устранение зависимости shutdown от PyQt/SIP финализации —
  отдельная открытая задача; автоматическое удаление Qt wrappers не добавлено,
  так как оно воспроизводимо падало на старых test-owned QObject.


### Продолжение 2026-10-11: локальный RTSP и reconnect встроенных источников

- [готово] Интеграционная RTSP-фикстура использует явно provisioned MediaMTX и FFmpeg, не загружает бинарник из теста, проверяет готовность publisher через `ffprobe` и пишет служебные файлы только во временный каталог. MediaMTX слушает loopback на динамическом TCP-порту; остальные listeners выключены.
- [готово] Документированы проверенная версия и checksum MediaMTX, инструменты и запуск тестов в `tests/RTSP_FIXTURE.md`.
- [готово] Локальные RTSP-тесты проверяют OpenCV и GStreamer в `thread` и `process` режимах, получение BGR-кадра с исходным `source_id`, потерю publisher и восстановление потока после его перезапуска.
- [готово] GStreamer thread monitor больше не считает `ASYNC/pending=PLAYING` отказом во время RTSP согласования. Он ждёт завершения startup в пределах init grace period; зависшее согласование после таймаута остаётся диагностируемым и запускает reconnect.
- [готово] После неудачного OpenCV reopen capture loop сохраняет работу и повторяет инициализацию с reconnect backoff. Ранее первая попытка во время отсутствия RTSP path останавливала поток и запрещала восстановление после появления path.
- [готово] Нормализация RTSP URL сохраняет нестандартный порт и IPv6 authority при подстановке userinfo. Тесты покрывают URL credentials, config credentials и IPv6.
- Проверки на сервере: `tests/unit/capture` — 70 passed; локальный RTSP source/reconnect набор — 8 passed; прежние RTSP capture-and-record тесты OpenCV и GStreamer — 2 passed.
- Следующий шаг: инвентаризировать встроенные processor/source/event компоненты, которые ещё запускаются в обход SPI, и проверить общий путь пользовательских тревог от detector до журнала. Отдельно остаётся выяснить и устранить native SIGSEGV PyQt при обычном завершении полного integration suite, описанный выше.


### Продолжение 2026-10-11: граница event detector runtime

- [готово] Проверен инвентарь plugin SPI: встроенные модули и event detectors регистрируются через общий registry; отдельная проверка inventory сохраняет 18 публичных config IDs и ноль legacy протоколов.
- [готово] Проверен путь пользовательской тревоги: entry point detector → `EventsService` → `EventsDetectorsController` → `EventsProcessor` → JSON adapter → универсальная строка журнала с типом, severity, source и details. Целевая группа plugin/alarm unit тестов завершилась: 23 passed. PostgreSQL запись, retry и идемпотентность по `alarm_id` покрыты отдельными integration тестами.
- Состояние на момент предыдущего аудита: event detector принимал только `thread`, поскольку `EventDetectorContext` содержал ссылки на live sources и `ObjectsHandler`. Этот пробел закрыт отдельным контрактом `EventUpdate` для новых process modules; legacy-детекторы с прямыми live-зависимостями остаются thread-only. `ObjectMultiCameraTracking` также остаётся thread-only как batch processor.
- Общая модель журнала поддерживает `AlarmEvent`, но live-проверка виджета с авторизованной пользовательской сессией не подтверждена; текущая проверка проверяет преобразование строки и JSON data source.
- [готово] Введён публичный `EventUpdate` и process-контракт `process_update(update, state)`. Host сериализует снимки active/lost объектов, process worker выполняет правило, возвращает события, а adapter сообщает об ошибке и переполнении очереди. Process event modules не могут объявлять live `object_handler`/capture dependencies.
- [готово] Spawn-тесты подтверждают передачу снимка с атрибутами и историей, доставку `AlarmEvent`, диагностику исключения плагина и ошибки старта, отказ process-режима без capability, видимую реакцию на переполнение обеих очередей и штатную остановку дочернего процесса и dispatcher thread.
- Ограничение: снимок передаёт метаданные объектов и краткие поля истории без изображения кадра. Сложные правила, которым нужен frame payload, остаются в thread mode до capability `event_frames` с ограниченными JPEG-вложениями. Для ложных/потерянных при аварии процесса тревог durable outbox по-прежнему не реализован.
- [готово] Process detector проходит через `EventsService` → `EventsDetectorsController` → `EventsProcessor` → JSON adapter → журнал data source; тест проверяет сохранённый `alarm_id` и преобразованный тип тревоги. PostgreSQL adapter отдельно покрыт тестами общего контракта alarm persistence.
- Следующий этап: спроектировать ограниченные по времени frame snapshots для Zone alarm detector, сохранить изображение доказательства через process-границу и затем мигрировать детекторы по одному с полным event-to-journal тестом. После этого провести live UI проверку при доступной авторизованной сессии.


### Продолжение 2026-10-11: миграция SystemEventsDetector

- [готово] Встроенный `SystemEventsDetector` переведён на `event_commands` и process worker. Контроллерские вызовы `emit_message/emit_started/emit_stopped` сохранены в adapter API; сообщения до старта дочернего процесса буферизуются и передаются после подтверждения готовности worker-а.
- [готово] Штатная остановка process event detector теперь ставит sentinel после принятых входов, вычитывает ответы worker-а и оставляет полученные события для финального `EventsDetectorsController.flush_once()`. Таймаут/ненормальный выход worker-а видны как degraded.
- [готово] Контрактные проверки покрывают SystemStart через builtin registry и service/controller, pre-start буфер, graceful drain и ранее добавленный process AlarmEvent путь до JSON журнала. На сервере запущено 45 целевых тестов: event runtime, legacy event detectors, builtin plugin inventory, plugin audit и alarm DB adapter; все прошли.
- [готово] Встроенный `CamEventsDetector` переведён на `source_updates` и process worker. `VideoCaptureBase` уведомляет подписчиков при регистрации disconnect/reconnect; `SourceModuleAdapter` передаёт сериализуемые переходы через `EventUpdate(kind="source_status")`. Проверены доставка события камеры через `EventsService` и controller, а также уведомления источника для обеих смен состояния.
- Следующий этап: спроектировать ограниченные по времени frame snapshots для Zone alarm detector. Кадры передаются только модулям с capability `event_frames`, как ограниченные JPEG-вложения; Zone ещё требует переноса геометрии и sticky enter/exit состояния.

### Продолжение 2026-10-11: миграция CamEventsDetector

- [готово] Для process event detector добавлена capability `source_updates`: runtime сериализует накопленные disconnect/reconnect переходы источников в `EventUpdate(kind="source_status")`.
- [готово] `VideoCaptureBase` вызывает уведомление подписчиков после записи перехода соединения. Вызовы из capture health path вынесены за `conn_mutex`, чтобы callback в runtime не удерживал блокировку соединения.
- [готово] Встроенный `CamEventsDetector` зарегистрирован process-only через новый модуль, а `EventsService` подписывает source-update detector на capture sources.
- Остаток миграции событий: Attribute перешёл на `event_frames`; Zone остаётся единственным встроенным event detector, который ещё требует image-aware process migration.


### Продолжение 2026-10-11: миграция ScheduleAlarmEventsDetector

- [готово] Встроенный ScheduleAlarmEventsDetector переведён на process-модуль с capability `event_updates`. Новый обработчик использует те же правила расписаний, фильтрацию по классам, cooldown и состояние активных/потерянных объектов.
- [готово] Object snapshot дополнен `time_detected` и `time_lost` как для текущего объекта, так и для записей истории. Это сохраняет поля `ScheduleAlarmEvent` и время начала/завершения старого детектора.
- [готово] Контрактный тест проходит через spawn worker, `EventsService` и `EventsDetectorsController`; проверены создание события при совпадении расписания и завершение события при потере объекта.
- Следующий детектор для миграции: Zone нуждается в кадрах доказательства и отдельном process-state для зон. Ограниченный JPEG transport уже реализован для Attribute; Schedule от него не зависит.


### Продолжение 2026-10-11: frame attachments и AttributeEventsDetector

- [готово] Добавлен публичный `EventFrameSnapshot`: JPEG хранится в бинарном вложении `EventUpdate`, декодирование ленивое, а размеры ограничены 2 MiB на кадр, 4 MiB на update и 16 кадрами. Worker queue для модулей `event_frames` ограничена четырьмя update-ами.
- [готово] `event_frames` разрешён только вместе с `event_updates`. Object snapshot содержит индексы текущего и sticky изображения; runtime дедуплицирует совместно используемые image buffers, не смешивая разные кадры с одинаковыми source/frame ids и отмечает ошибку/деградацию при превышении лимита.
- [готово] Встроенный `AttributeEventsDetector` переведён на process module. Контрактная проверка проходит через spawn worker и EventsService/controller; проверено, что изображения начала и завершения события доходят как сжатые вложения и декодируются в прежний BGR формат.
- Остаток: `ZoneEventsDetector` требует переноса геометрии зон, тайм-порогов, возврата в зону и sticky изображения начала события на процессное состояние. Это последнее встроенное событие с live `ObjectsHandler` dependency.


### Продолжение 2026-10-11: миграция ZoneEventsDetector

- [готово] Zone переведён на process runtime и использует прежний алгоритм геометрии, порогов входа/выхода, возврата в зону и завершения по потере объекта через синхронный `_process_once`. Worker получает active/lost snapshots, историю трека и кадры как ограниченные JPEG-вложения; sticky evidence хранится внутри worker.
- [готово] Изменения зон из UI и API проходят через `EventDetectorModuleAdapter.submit_command` и сериализуемый `EventUpdate(kind="module_command")`; новые/удалённые зоны и пороги отражаются в конфигурации runtime. UI-подписки EventService удаляет при release.
- [готово] Состояние активных зон теперь индексируется парой `(source_id, object_id)`. Регрессия подтверждает, что потеря объекта с одинаковым локальным ID на одной камере не завершает тревогу другой камеры.
- [готово] Lazy image proxy ZoneEvent исправлен для pickle между spawn worker и основным процессом. Проверен process-путь обнаружения, enter/exit и закрытие события при потере объекта с сохранением кадра доказательства.
- [готово] Исправлен EventsProcessor: первое активное долгосрочное событие теперь сохраняется адаптером, когда до этого не было активных событий такого типа. Регрессия проверяет JSON-запись ZoneEvent и кадр доказательства.
- Проверки миграции Zone на сервере: 138 целевых тестов прошли. Headless smoke поднял capture и все пять встроенных event workers, захватил 10 кадров; веб-сервер не был включён в тестовой конфигурации.
- [готово] Исправлено зависание MpControl.stop() после принудительного завершения worker-а: runtime больше не drain-ит потенциально повреждённые IPC очереди и не ждёт их feeder threads без ограничения. Принудительное завершение и отказ от очереди явно отражаются в журнале.
- [готово] EventDetectorModuleAdapter не помечает нормальный exit worker-а во время shutdown как отказ компонента.
- Проверки lifecycle-фикса на сервере: 4 целевых test-файла прошли; PipelineSurveillance model-backed finite-video E2E прошёл в режимах thread и spawn-process (2 passed). Headless smoke повторно завершился с Application finished with code: 0, без watchdog SIGKILL и без ложной ошибки event worker. В коротком smoke YOLO не успевает закончить инициализацию до EOF, поэтому он завершается принудительно с явной диагностикой; обработку кадров закрепляет отдельный 20-кадровый E2E. Web UI не проверялся, так как web server отключён в конфигурации smoke.
