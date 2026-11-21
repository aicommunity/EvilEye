# План завершения миграции расширяемых модулей EvilEye

## Актуальный срез выполнения на 2026-10-13

Этот раздел заменяет более ранние статусы ниже. Исторические журналы сохранены
для контекста, но не являются текущим чек-листом.

- Полные тесты после проверки HEAD `4d0019a`: unit-набор прошёл, integration-
  набор завершился с кодом 0. Integration suite пропускает проверки, для которых
  на сервере нет MediaMTX, `v4l2loopback`, RTSP-секретов или модельных файлов.
- Исправлен найденный полным unit-прогоном дефект process transport: адаптер не
  переносил `frame_version` в descriptor и обратно. `frame_version` добавлен в
  список метаданных; целевой тест и полный unit-набор после исправления прошли.
- External package установлен editable в отдельный virtualenv без переустановки
  EvilEye. Пример pipeline проходит lifecycle, а `example/add-label` добавляется
  в `PipelineSurveillance` через `extend` и `replace` в thread и spawn-process;
  проверены shared-frame transport и сохранение метаданных кадра.
- Без inference выполнены микрозамеры плагинного runtime. Для 1920×1080 процессный
  round-trip: p50 6.316–6.778 мс, p95 7.053–7.920 мс; потоковый: p50 0.607–0.634
  мс, p95 0.681–0.692 мс. Методика и ограничения приведены в
  `docs/PLUGIN_RUNTIME_BENCHMARK.md`. Это измерение runtime, а не сравнение со
  старой реализацией и не замена end-to-end SLA.
- Визуальная проверка браузера с реально отображённой синтетической тревогой не
  завершена: средство Windows browser automation остановило этот сценарий, так как
  не смогло надёжно определить текущий URL. API и ACL-путь тревоги покрыты
  автоматическими проверками; браузерный пункт остаётся открытым.

### Оставшиеся критерии первой версии

1. Зафиксировать целевые FPS, p95 задержку, допустимую долю потерь и полноту тревог;
   затем сравнить старый и новый runtime на одних кадрах, моделях и настройках.
2. Проверить поведение тревоги в настоящем браузерном экране: тип, время, камера,
   серьёзность, детали и положительный/отрицательный camera ACL.
3. Повторить network disconnect/reconnect на локальном RTSP fixture. В текущем
   серверном окружении MediaMTX отсутствует, а управление `v4l2loopback` запрещено;
   текущий integration прогон эти сценарии пропустил.
4. Сохранить полный тестовый прогон и внешний package smoke как повторяемые команды
   CI или release gate; после каждого изменения проверять shutdown и отсутствие
   оставшихся worker-ов.
5. Поддерживать документацию в соответствии с кодом; текущий раздел миграции в
   `docs/PIPELINE_ARCHITECTURE.md` уже исправлен, результаты микробенчмарка вынесены
   отдельно.

Durable alarm outbox после аварийного завершения, универсальный DAG, hot-plug,
автоустановка зависимостей, sandbox стороннего Python-кода и process execution для
синхронного `ObjectMultiCameraTracking` остаются вне первой версии. Python-плагин
исполняется с правами процесса EvilEye; process mode не является границей
безопасности.

## Предыдущий срез проверок на 2026-10-12 (исторический)

Этот срез отражает фактически выполненные проверки и уточняет статусы в более ранних хронологических разделах ниже.

| Пункт | Статус и подтверждение |
| --- | --- |
| 1. Сверка плана с кодом и проверками | Выполнена. SPI, инвентарь встроенных модулей, ограничения runtime и отложенный durable outbox описаны в этом документе и `docs/PLUGINS.md`. |
| 2. Авторизованный WebUI | Ранее функциональный сценарий пройден на локальном видео: временный пользователь открыл live-кадр YOLO, журнал и playback с MP4-сегментом; тревоги в том интервале не возникли. В изолированном managed-run smoke авторизация, /ready и PipelineSurveillance были исправны. Первоначальный total=0 объяснился ACL: аккаунту без разрешённых камер запись правильно не показывалась. Пользователь с allowed_cameras=Cam0 тоже не видел её, потому что JSON alarm мог содержать source_id без source_name. Исправлено сопоставление ID камеры с именем из PipelineSurveillance; сквозная регрессия проверяет process detector → JSON adapter → авторизованный пользователь Cam0 → grouped journal API. Повторный managed-run smoke после исправления вернул одну строку ppe_violation с source=Cam0. После этого Runs UI визуально проверен в браузере на изолированном сайте с синтетическим degraded runtime: панель показывает health и раскрываемые сведения о модулях. Отрисовка реальной тревоги в журнале в браузере отдельно не проверялась. Тестовый сайт/пользователи удалены, сервер и worker остановлены. |
| 3. Source/frame контракты | Пройдены unit и GStreamer frame-contract проверки. Синтетический RTSP recovery прогон прошёл 8 случаев: OpenCV/GStreamer, thread/process и восстановление публикации после остановки. Физическое отключение камеры этим тестом не моделировалось. |
| 4. Внешний пакет плагина | Пройдена установка отдельного editable-пакета в чистое virtualenv, discovery entry point и запуск `process_item` в spawn worker с корректной остановкой. EvilEye в это окружение не переустанавливался. Для PEP 660 editable install нужен актуальный pip. |
| 5. Длительная live-нагрузка | Двухминутный прогон RTSP камеры Cam1 с двумя process YOLO и per-camera BoT-SORT выполнен; multi-camera tracker был выключен. При `desired_fps=5` получено 7.05 source FPS, 6.93 detector FPS и 2.02 tracker FPS. Отдельный RTSP PTS probe измерил примерно 10.06 FPS без декодирования; детали и профиль стоимости GMC/ReID — `reports/tracker_stream_fps_investigation_2026-10-12.md`. |

### Дополнительные regression-проверки на 2026-10-12

- Process detector → EventsProcessor → JSON alarm adapter → /api/v1/journals/events/grouped: проверены пользовательский тип тревоги, время, источник и структурированные детали. В том же пути тест самостоятельно регистрирует module spec, поэтому не зависит от порядка запуска suite.
- Полный unit-набор после исправления: QT_QPA_PLATFORM=offscreen python3 -m pytest -q tests/unit завершился с кодом 0; коллекция содержит 1071 тест. Полный integration-набор: QT_QPA_PLATFORM=offscreen python3 -m pytest -q tests/integration завершился с кодом 0; коллекция содержит 378 тестов. Опциональные model-parity, model-process, физический RTSP/v4l2loopback и real-data тесты пропускаются без соответствующих моделей, секретов или системных возможностей.
- Управляемый Web/API smoke на изолированном сайте подтвердил аутентификацию, /ready=200 и активный PipelineSurveillance. Диагностика тревоги показала: admin видел запись (total=1), пользователь без ACL — нет (ожидаемо), а пользователь с allowed_cameras=[Cam0] также не видел её, поскольку поле source_name в JSON тревоге было пустым. JsonLabelJournalDataSource теперь восстанавливает имя из source_id и карты источников конфига до ACL-фильтрации. Регрессия process alarm с ограниченным пользователем Cam0 проходит от detector до grouped API; после исправления повторный managed-run smoke вернул total=1, событие ppe_violation и source=Cam0. Визуальный smoke Runs UI выполнен на изолированном сайте с синтетическим degraded runtime; панель показывает health и JSON-диагностику. Отрисовка реальной тревоги в журнале отдельно не проверялась.
- Управляемая остановка проверена настоящим process group: ConfigRunManager посылает SIGTERM владельцу, владелец закрывает дочерний worker, прямой сигнал worker-у не отправляется. Целевой набор process control, ConfigRunManager и новая integration-регрессия прошёл: 24 теста.
- Alarm/event detector и journal API наборы прошли совместно: 18 тестов. Проверки выполнялись на сервере; пользовательские изображения и тестовые артефакты в коммит не включались.

### Наблюдения эксплуатации

Во время UI-прогона конфигурация с неограниченным 30 fps локальным источником, YOLO и event detectors перегружала очереди: runtime явно зарегистрировал вытеснение устаревших кадров и переполнение очереди Zone detector, установив degraded-состояние. Это подтвердило видимость перегрузки, но такой прогон нельзя считать проверкой производительности штатной камеры.

Первый тяжёлый прогон выявил фактическую ошибку остановки: общий `terminate_tree` посылал SIGTERM всему process group, из-за чего event workers получали сигнал до graceful drain контроллера и сообщали `worker exited abnormally during shutdown`. Введён `terminate_tree_gracefully`: сначала сигнализируется только владелец run, который останавливает модули и очереди; оставшаяся process group получает SIGKILL только по истечении grace period. Повтор managed-run прогона завершился штатно примерно за 5 секунд, без ошибок event workers, SIGKILL и оставшихся процессов. Профильные unit-проверки process control, ConfigRunManager, stack_control и scheduler crash resilience прошли успешно.

Для PEP 660 в свежем virtualenv сначала потребовалось обновить pip. `docs/PLUGINS.md` и README примера теперь предписывают обновление pip перед editable install. Durable outbox и гарантия доставки тревоги через аварийный перезапуск по-прежнему отложены.


## Цель и направление

Довести встроенные компоненты и пайплайны до одного публичного Plugin SPI. Встроенные реализации остаются в репозитории и становятся контрольными примерами для внешних пакетов. `PipelineSurveillance` остаётся специализированным, но расширяемым пайплайном; `PipelineDeclarative` — простым последовательным пайплайном. В первой версии не вводить универсальный DAG, hot-plug и автоматическую установку зависимостей в работающем процессе.

Работы вести на серверной ветке `plugin_support`; каждый проверенный этап фиксировать отдельным коммитом. Пользовательские неотслеживаемые файлы не включать. До фиксации миграции этап должен иметь контрактные тесты, диагностику ошибок, запуск штатных конфигураций и подтверждённую остановку процессов.

## Текущее состояние кодовой базы

### Уже реализовано

- `evileye/core/plugins.py` содержит `PluginSpec`, `ModuleSpec`, `PipelineSpec`, `PluginRegistry` и загрузчик entry points группы `evileye.plugins`; есть проверка API version, фабрик, видов модулей, режимов и идентификаторов.
- Встроенные классы регистрируются через `register_module`; старый `EvilEyeBase.register` остаётся совместимым фасадом. Параллельный `EvilEyeBase._registry` удалён. Публичные экспорты `evileye.core` и `evileye.object_detector` загружаются лениво; пайплайны явно импортируют встроенные группы для регистрации при старте, чтобы spawn-worker не импортировал все реализации и тяжёлые ML-зависимости.
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
5. [готово] Golden parity закрепляет YOLO, RT-DETR, AttributeDetector, AttributeClassifier и BoT-SORT. Для AttributeClassifier bbox допускает 0.01 px и confidence 1e-4 из-за измеренного влияния глобального CPU thread count Ultralytics; class ID проверяется точно. Отдельные контракты проверяют ordered output в thread/process, TrackingDTO из dict/wrapper, inference DTO в tracker и batch metadata.

**Критерий:** ни один штатный детектор, tracker или attribute module не требует `LegacyProcessorModuleAdapter`; thread/process режимы проходят один набор контрактных сценариев.

### Этап C. Мигрировать источники без потери capture-функций

1. [частично] Контракт Frame документирует размеры/цветовой формат, timestamp, sequence, connection generation и владение shared-frame handle; descriptor round-trip, внешний open/read/close, GStreamer MP4 PTS/file-loop и синтетический RTSP recovery проверены в thread/process. На сервере кадры получены с трёх доступных камер через OpenCV и GStreamer. Принудительное сетевое отключение физических камер не выполнялось; reconnect проверяется синтетическим RTSP fixture.
2. [готово] OpenCV и GStreamer подключены к source SPI через `SourceModuleAdapter`. Их codec handling, reconnect, split/crop, запись сегментов, ограниченные очереди и shared-frame capture остаются в специализированных backend-ах.
3. [готово] Встроенные capture backend-ы исполняют захват в заявленном thread/process режиме; сторонние source plugins используют общий thread/spawn runtime. SourceModuleAdapter публикует capture health и worker status. Тесты закрепляют open/close при EOF, process shutdown, диагностику зависшего thread и blocking process. Для встроенного GStreamer проверены получение кадра и запись MP4 через SourceModuleAdapter с backend process; дочерние worker-ы завершаются штатно. Parent proxy передаёт в metadata кадра переходы доступности и backend_connection_generation.
4. [готово для доступных backend-ов] Остановка проверена в thread/process тестах, полном unit suite и live RTSP smoke без оставшихся worker-ов. Локальный RTSP fixture прошёл 8 тестов на OpenCV/GStreamer в thread/process; доступные физические камеры выдали кадры через оба backend-а. Принудительное отключение работающей физической камеры оставлено вне проверки.

**Проверки:** видеофайл, loop/reconnect, синтетический RTSP и доступные реальные камеры; запись и ffprobe; проверка отсутствия worker, сокетов и очередей после stop.

### Этап D. Завершить batch и event/alarm lifecycle

1. [готово] `ObjectMultiCameraTracking` использует batch SPI с явной синхронизацией и ограничением `thread`-режима; контракт покрыт unit-тестами.
2. [готово] Фабрики и lifecycle Event detectors используют PluginRegistry, EventDetectorContext и общий runtime-адаптер. Все встроенные event detectors работают в process через сериализуемые capabilities event_updates, source_updates, event_commands и event_frames; EventsService управляет зависимостями, запуском и освобождением. Для пользовательского process detector-а обязательно объявить совместимую capability и сериализуемый контракт.
3. [готово для JSON и PostgreSQL] AlarmEvent проходит от стороннего detector-а через контроллер, оба persistence adapter-а и модель журнала. PostgreSQL integration tests проверяют запись, уникальность по alarm_id, retry и восстановление после управляемого сетевого отказа; unit tests проверяют общий формат строки журнала. Process detector → JSON → /api/v1/journals/events/grouped покрыт сквозной регрессией; отдельный браузерный снимок реальной тревоги не получен, поскольку предыдущий live smoke не породил alarm.
4. [готово для v1] Регрессии проверяют изоляцию упавшего detector-а от соседнего правила, в том числе process worker: соседний detector публикует тревогу, а упавший остаётся degraded. EventsDetectorsController агрегирует runtime status и причины отказа по каждому detector-у, публикует общий degraded status в runtime stats и debug_info, защищает совместное состояние блокировкой; тест проверяет, что отказ одного process worker не мешает соседу опубликовать тревогу и доступен через диагностику контроллера. Проверены ограничение очереди, retry и восстановление PostgreSQL после управляемого отказа, drain принятых batch-ей, restart, timeout и degraded при постоянной потере/переполнении. Durable outbox после исчерпания retries не реализуется в v1: событие не гарантируется при аварийном падении до записи.

**Критерий:** внешний event/alarm detector не меняет ядро для нового события и проходит до выбранного хранилища и общего представления в журнале; режим исполнения и отказ detector-а диагностируются явно.

### Этап E. Свести пайплайны к реестру и проверить внешний пакет

1. [готово] `PipelineSurveillance`, `PipelineCapture` и `PipelineDeclarative` зарегистрированы как builtin `PipelineSpec`; `PipelineService` разрешает их через PluginRegistry.
2. [готово] `pipeline_class` сохранён как compatibility alias; неизвестный выбранный pipeline приводит к диагностируемой ошибке без fallback.
3. [готово] Оставить `PipelineSurveillance` фиксированным графом стадий; порядок, правила `extend`/`replace`, несколько детекторов на один источник и ограничения thread-only стадий описаны в `PLUGINS.md` и `PIPELINE_ARCHITECTURE.md`.
4. [готово] Минимальный внешний пакет установлен editable-режимом в изолированное server-side virtualenv; entry point `evileye.plugins` обнаружен, модуль зарегистрирован без изменения/переустановки EvilEye. В example package указан build backend с PEP 660 поддержкой.
5. [готово] Контрактные тесты покрывают конфликт ID, неизвестный module/pipeline, неверную API version, общую ошибку импорта, отсутствующую зависимость с указанием entry point и имени пакета, неверный IPipeline и отказ без fallback.

**Критерий:** builtin и внешний pipeline разрешаются тем же API; сторонний package обнаруживается после перезапуска приложения.

### Этап F. Полный regression и эксплуатационная проверка

1. [готово] Последние полные прогоны: tests/unit (1 044 теста) и tests/integration (375 тестов) завершились с exit 0; после прогонов дочерних worker-ов не осталось.
2. [готово] Headless Qt suite работает с QT_QPA_PLATFORM=offscreen; весь tests/integration/visualization завершился обычным exit 0 без принудительного выхода.
3. [готово для проверенных сценариев] Finite-video PipelineSurveillance с детектором, tracker-ом и ffprobe прошёл в thread/spawn-process. Все три доступные RTSP камеры выдали BGR кадры через OpenCV и GStreamer; live запись MP4 прошла и в обычном backend, и через process-режим SourceModuleAdapter. Синтетический RTSP recovery проверен отдельно.
4. [частично] Авторизованный WebUI smoke с временным пользователем подтвердил live-кадр с YOLO и воспроизведение созданного MP4 через playback. API contract пользовательской тревоги проверен отдельно; визуальный browser smoke именно со сработавшей тревогой ещё не выполнен. Защищённые API и playback работали с тестовой учётной записью; временный пользователь удалён после проверки.
5. [готово] Inventory gate фиксирует все 17 builtin manifest IDs и alias ObjectDetectorYoloMp; встроенных legacy_processor_protocol и legacy_source_protocol нет. Thread-only исключение ObjectMultiCameraTracking задекларировано как batch_processor.

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
- ObjectDetectorRfdetr переведён на processor_item с отдельным RF-DETR runtime. Поддержаны nano/small/medium/large, native Supervision result, class filtering и ROI mapping и num_detection_threads через ordered worker_count pool; неизвестная модель и некорректная batch cardinality вызывают явную ошибку. На сервере реальная локальная модель успешно прошла opt-in smoke в spawn worker. RF-DETR объявляет только `process`: thread smoke воспроизвёл нативный abort внутри Matplotlib/Supervision import, поэтому неподдержанный режим теперь отклоняется до старта.
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

## Исторический порядок оставшихся работ на 2026-10-11

На тот момент первая версия плана **не была завершена**. Registry/SPI, встроенные item модули,
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

- [готово] Модель кадра и владение shared-frame handle документированы и покрыты descriptor round-trip и source-контрактами. Дополнительно пройдены unit/GStreamer frame-contract проверки и синтетический RTSP recovery на обоих backend-ах и в обоих execution modes; подробный состав и ограничение теста указаны в актуальной сводке выше.
- [готово] Полный `PipelineSurveillance` finite-video test считает уникальные frame IDs на source/detector/tracker stage и проверяет равенство множеств без повторной выдачи последнего кадра. Записанный сегмент читается `ffprobe`; detector/tracker проверены в thread и spawn-process после дедупликации source SPI.
- [готово] GStreamer local MP4 loop и синтетический RTSP stop/restart проверяют connection generation, уникальные frame IDs и восстановление источника для поддерживаемых backend-ов и execution modes. Проверка физического отключения камеры не входит в synthetic fixture.
  Синтетический RTSP прогонять независимо от доступности реальных камер; реальные
  RTSP результаты фиксировать отдельно для каждого backend и transport.

**Готово, когда:** finite-video прогон доказывает прохождение кадров по стадиям и
корректное освобождение ресурсов в thread/process режимах.

### 3. Зафиксировать границу event/alarm runtime

- [готово] Ограниченные очереди тревог проверяются при временном отказе БД и burst из 256 событий: размер очереди не превышает заданный максимум, лишние события явно отклоняются, принятые записи сохраняют FIFO, stop дренирует их; bounded retry и alarm_id обеспечивают наблюдаемый отказ без дубликатов.
- [готово] Падение одного process event detector не останавливает соседнее правило; ошибка видна в runtime stats и debug_info, общий controller health становится degraded. Это закреплено контрактным тестом.
- [готово] Пользовательские process event detectors используют сериализуемый EventUpdate/process_update контракт; live зависимости ObjectsHandler и capture sources остаются thread-only и отвергаются валидатором для process mode. Unit-тесты проверяют оба пути.

**Готово, когда:** отказы и восстановление БД/детекторов наблюдаемы; ограничение
для live-зависимостей в process режиме и доставка через EventUpdate описаны и
проверены контрактными тестами.

### 4. Закрыть regression и эксплуатационные проверки

- [готово] Устранён нативный SIGSEGV Qt при обычном выходе visualization suite. Полные integration-прогоны завершились с exit 0; подтверждено штатное завершение pytest и worker-ов.
- [готово] Повторно пройдены полный unit и integration наборы, finite-video E2E, plugin-package smoke и opt-in реальные model/process smoke; проверены коды завершения и отсутствие оставшихся worker-ов.
- [готово] Web UI проверен с временной ограниченной учётной записью: live кадр с YOLO, журнал и воспроизведение реального MP4 сегмента доступны после входа. Журнал в интервале проверки был пуст, поэтому отрисовка строки тревоги в браузере отдельно не подтверждена. Тестовый пользователь удалён после проверки.
- [готово] Inventory gate фиксирует 17 builtin manifest IDs, capabilities и execution modes; число `legacy_processor_protocol`/`legacy_source_protocol` равно нулю, thread-only batch исключение документировано.

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
- Полный integration suite и авторизованный просмотр Web UI остаются открытыми. Локальные RTSP fixture/reconnect с OpenCV и GStreamer теперь прошли в thread/process режимах; live RTSP кадр и запись также проверены. AttributeClassifier parity и process smoke добавлены и проходят; общая миграция не завершена.

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
   - [готово 2026-10-12] EventsProcessor.get_runtime_stats() включает health и
     counters DB adapters; защищённый GET /api/v1/system/runtime передаёт
     pipeline/event runtime через control IPC, а Runs UI показывает общий health
     и раскрываемые данные для runtime:view. Backend API и IPC проверены.
   - [готово 2026-10-12] UI собран временным официальным Node.js v24.21.0: `npm run build` прошёл, включая `tsc --noEmit` и Vite production build. Затем Runs UI проверен в браузере на изолированном сайте с синтетическим degraded runtime; health badge и раскрываемая диагностика компонентов отобразились. Это проверка отображения; backend API/IPC проверен отдельными тестами.
   - [ограничение v1] Process event detector требует сериализуемых capabilities
     event_updates/event_commands. Подписки на live ObjectsHandler и capture
     sources остаются thread-only; несовместимая process-конфигурация отклоняется.
   - [готово 2026-10-12] JSON alarm без source_name получает имя камеры из source_id и карты источников PipelineSurveillance до ACL-фильтрации. Сквозной тест аутентифицирует ограниченного пользователя с доступом к Cam0 и проверяет alarm от process detector до grouped journal API.
2. **Закрыть source transport.**
   - [готово] Live frame tests проходят через GStreamer и OpenCV SPI на камерах
     `.199` и `.200`; GStreamer shared recorder записал MP4 с пакетами на обеих
     камерах. OpenCV проверки используют CAP_FFMPEG.
   - [готово 2026-10-12] Временный локальный MediaMTX fixture проверил
     DESCRIBE/SETUP/PLAY, timeout и reconnect OpenCV/GStreamer: 8 тестов прошли
     в thread/process режимах. Физическое отключение камеры этим не проверяется.
3. **Закрыть полный integration shutdown.**
   - [готово 2026-10-12] Полные unit и integration наборы завершились с кодом 0:
     1071 и 378 тестов в коллекции соответственно. После обоих прогонов не
     осталось pytest, API server или process worker процессов.
   - [ограничение окружения] Тесты, требующие моделей, RTSP-секретов,
     MediaMTX/v4l2loopback или real-data, пропущены и не считаются выполненными.
   - [правило] Повторять полный regression после каждого дальнейшего изменения;
     optional live/model smoke запускать только при наличии заявленных ресурсов.
4. **Закрыть эксплуатационную часть.**
   - [готово для проверенных режимов] Finite-video PipelineSurveillance
     проверил detector/tracker и MP4 через ffprobe в thread/process; доступные
     физические камеры выдавали кадры через OpenCV и GStreamer, запись проверена
     отдельно. Web UI с временной учётной записью проверил live и playback.
   - [нужно эксплуатационное решение] Двухминутный live fanout на текущем
     сервере показал degraded под нагрузкой: 7.05 FPS источника, 6.93 FPS после
     detector fanout и 2.02 FPS после tracker, с потерями и incomplete fanout.
     Нужны целевая частота/полнота для safety alarm и выбранная политика, затем
     повторный прогон по этим критериям. Измерения не являются SLA/KPI.
   - [готово 2026-10-12] Runs UI диагностика собрана и визуально проверена в
     браузере на изолированном сайте с синтетическим degraded runtime. Физическое
     отключение рабочей камеры не выполнялось, чтобы не нарушить совместную эксплуатацию.
5. **Завершить inventory миграции.**
   - [готово 2026-10-12] Gate фиксирует 17 builtin module IDs, capabilities и
     execution modes; legacy_processor_protocol/legacy_source_protocol равны
     нулю. ObjectMultiCameraTracking документирован как batch_processor с
     ограниченным execution mode; inventory и shutdown проверены.

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
- Проверки lifecycle-фикса на сервере: 4 целевых test-файла прошли; PipelineSurveillance model-backed finite-video E2E прошёл в режимах thread и spawn-process (2 passed). Headless smoke повторно завершился с Application finished with code: 0, без watchdog SIGKILL и без ложной ошибки event worker. Первоначальный smoke показал, что EOF может наступить до завершения inference и worker принудительно останавливается; продолжение 2026-10-12 добавило readiness gate и drain конечного source. Web UI не проверялся, так как web server отключён в конфигурации smoke.


### Продолжение 2026-10-12: readiness, конечный EOF и shutdown событий

- [готово] PipelineProcessors.start() ждёт фактической инициализации item workers перед запуском source processors. Для встроенного YOLO smoke подтвердил, что модель загружена до старта capture; SourceModuleAdapter открывает backend только из source worker, поэтому кадры не производятся во время ожидания detector-а.
- [готово] Item runtime учитывает submitted/in-flight работу, включая результат None и вытесненный кадр. MpControl повторяет постановку после вытеснения с коротким bounded wait, чтобы гонка multiprocessing queue не превращала stale-frame drop в отказ всей стадии. PipelineProcessors собирает backlog по runtime stats и очередям стадий. При autoclose конечные источники дают pipeline время на drain; EVILEYE_AUTOCLOSE_DRAIN_TIMEOUT_SEC ограничивает ожидание 60 секундами по умолчанию и сообщает оставшиеся модули при timeout.
- [готово] Shutdown событий переставлен: сначала прекращается фоновый опрос event detectors, затем выполняется финальный flush, после чего останавливаются worker-ы и адаптеры. Smoke больше не воспроизводит гонку чтения закрытой multiprocessing queue.
- Целевые unit-тесты runtime, capture source lifecycle, readiness и controller shutdown: 68 passed. Model-backed PipelineSurveillance finite-video E2E: 2 passed (thread и spawn-process).
- Headless запуск на сервере завершился с Application finished with code: 0: readiness была до EOF; autoclose дождался detector-а, worker завершился штатно с processed_total=9, без forced termination, shared-frame transport ошибок и ошибки закрытой event queue. Источник захватил 10 кадров; один кадр был явно отброшен ограниченной очередью как устаревший при перегрузке (input_queue_dropped=1). Это сохраняет текущую bounded/drop-oldest политику и не является гарантией обработки каждого кадра реального времени.
- Web UI в smoke не проверялся: конфигурация запуска headless и веб-сервер отключён.


### Продолжение 2026-10-12: локальный RTSP recovery

- [готово] Временный MediaMTX 1.21.0 provisioned в /tmp только для проверки; SHA-256 архива совпал с опубликованной в tests/RTSP_FIXTURE.md контрольной суммой. Бинарник и конфигурация не добавлялись в репозиторий.
- [готово] tests/integration/capture/test_local_rtsp_sources.py: 8 passed для OpenCV и GStreamer в thread/process: первичная доставка кадра и восстановление после остановки/повторного запуска publisher-а. Recovery проверяет рост backend_connection_generation.
- Ограничение: это синтетический RTSP источник loopback. Поведение на конкретных камерах проверялось ранее отдельно; Web UI и полный integration suite остаются открытыми.


### Продолжение 2026-10-12: Qt GUI lifecycle в integration tests

- [готово] Тесты журнала событий используют общую session-фикстуру QApplication. Удалено создание второго QApplication в тестах double-click и realtime updates; тесты больше не вызывают quit/exit для общего приложения.
- [готово] Удалён отложенный callback из теста кнопки журнала: он мог исполниться уже во время следующего теста и обходить устаревшие QWidget wrappers. В realtime/double-click тестах закрытие выполняется напрямую; таймеры singleShot, которые не могли сработать при заблокированном event loop, больше не оставляются в очереди.
- Проверка: вся группа tests/integration/visualization/events_journal — 29 passed, exit 0; git diff --check — без ошибок.
- Открытый сбой: весь tests/integration/visualization доходит до выполнения тестов, затем обычный выход Python завершается SIGSEGV (exit 139). GDB показывает PyQt6.QtCore cleanup_qobject → sip_api_visit_wrappers → cleanup_on_exit → Py_FinalizeEx; Python-кадра в момент падения нет. Опциональный EVILEYE_PYTEST_FORCE_EXIT здесь не включался и не считается исправлением. Удаление Qt wrappers вручную пробовалось и само приводило к native crash, поэтому в продукте и общей фикстуре такое удаление не добавлено.
- Дальше: изолировать оставшийся dangling QObject wrapper в смешанном запуске Configurer и journal GUI тестов; проверить lifecycle дочерних виджетов и QSqlQueryModel без принудительного завершения процесса, затем повторить весь visualization suite и общий integration suite.


### Продолжение 2026-10-12: единый QApplication для visualization suite

- [готово] Добавлена session-scoped autouse QApplication фикстура для tests/integration/visualization; на headless сервере она заранее выставляет QT_QPA_PLATFORM=offscreen. Все GUI-тесты получают singleton до своего setup.
- [готово] 44 прямых вызова QApplication([] или sys.argv) приведены к проверке существующего singleton; из visualization-тестов удалены локальные app.quit/exit (ни один из этих тестов не запускает app.exec). Это предотвращает повторное создание приложения и остановку общего Qt runtime.
- Проверка: 144 теста из configurer, events_journal, roi_core, roi_editor завершились с exit 0. Коллекция полного visualization набора — 215 тестов; запуск дошёл до [100%], без FAILED/ERROR в логе, но затем завершился exit 139 во время выгрузки Python.
- Открытый сбой не изменился: нативное завершение происходит в PyQt6/SIP cleanup_qobject → sip_api_visit_wrappers → cleanup_on_exit → Py_FinalizeEx, без Python stack frame. Единый QApplication и снятие дублирующих create/quit устранили один класс lifecycle-ошибок, но не dangling wrapper, вызывающий финальный SIGSEGV.
- Следующее действие: найти владельца повреждённого QObject wrapper или подтвердить дефект версии PyQt6 в изоляции минимальным воспроизведением; оставить EVILEYE_PYTEST_FORCE_EXIT только диагностическим обходом, не считать его исправлением.


### Продолжение 2026-10-12: Configurer cleanup и обычный выход GUI suite

- В ConfigurerMainWindow список подключений сигналов отслеживания изменений теперь сохраняется. При подтверждённом закрытии окна слоты отключаются до закрытия вкладок; это устранило воспроизводимый SIP crash при создании полного набора вкладок и завершении отдельного процесса.
- Упрощён smoke-тест Configurer: удалён QTimer.singleShot вместе с блокирующим time.sleep, закрытие окна выполняется синхронно, а реальное создание и завершение GUI выполняется дочерним процессом. Родительский pytest проверяет его код возврата и вывод при ошибке.
- Проверки на сервере: одиночный Configurer smoke — 1 passed, exit 0; совместные Configurer и event journal — 30 passed, exit 0; весь tests/integration/visualization — 215 collected, 180 passed, 35 ожидаемо skipped (тесты с реальными данными выключены), exit 0. EVILEYE_PYTEST_FORCE_EXIT не использовался.
- Предыдущий нативный SIGSEGV полного visualization suite больше не воспроизводится. Следующий шаг по плану: повторить полный integration suite и зафиксировать оставшиеся внешние/средовые блокеры, затем вернуться к финальной проверке inventory thread/process и parity.


### Продолжение 2026-10-12: gate встроенного plugin inventory и общий integration suite

- Inventory gate теперь проверяет точное множество 17 builtin manifest IDs, их ModuleSpec.kind и список execution modes. Factory из тестовых модулей не попадают в builtin inventory, даже если legacy decorator зарегистрировал их под plugin_id=evileye.
- Process contract тест расписания запускается для обоих ID: ScheduleAlarmEventsDetector и совместимого FieldOfViewEventsDetector. Проверены создание через EventsService, process worker, тревога начала события, завершение по потере объекта и shutdown для каждого ID.
- Полный tests/unit: 1 039 collected, все прошли, exit 0.
- Полный tests/integration: 373 collected, 312 passed, 61 skipped, exit 0. Пропуски относятся к выключенным model parity/real-data сценариям, отсутствующему MediaMTX binary, запрету загрузки v4l2loopback и отсутствующим live RTSP credentials. Это успешный общий shutdown для доступной части набора, но перечисленные внешние проверки остаются неподтверждёнными этим запуском.
- После обоих прогонов pytest, spawn workers и multiprocessing resource tracker не остались запущенными.
- Следующий шаг: повторно обеспечить локальный RTSP fixture на сервере без системной установки; включить model parity/E2E проверки при доступных моделях; отдельно подтвердить live camera/Web UI проверки. После этого обновить финальный inventory matrix и критерии завершения v1.


### Продолжение 2026-10-12: модельная parity и process/E2E проверки

- [готово] После полного unit/integration прогона повторно выполнены четыре opt-in golden parity теста для YOLO, RT-DETR, AttributeDetector и AttributeClassifier: все завершились с exit 0. Для AttributeClassifier зафиксирован ограниченный численный допуск: Ultralytics меняет глобальный лимит CPU-потоков PyTorch с 16 на 8, что даёт измеренный сдвиг bbox менее 0.01 пикселя и confidence менее 1e-4. Тест сохраняет точную проверку class ID и проверяет координаты/уверенность в этих пределах; это не допускает смещения даже на целый пиксель.
- [готово] AttributeDetector и AttributeClassifier spawn-process smoke: 4 passed, exit 0.
- [готово] PipelineSurveillance finite-video E2E повторён отдельно: thread и spawn-process — 2 passed, exit 0; worker-ы штатно завершаются.
- [готово] Локальный MediaMTX RTSP fixture восстановлен во временном каталоге и проверен по SHA-256 из `tests/RTSP_FIXTURE.md`. OpenCV/GStreamer RTSP lifecycle и reconnect: 8 passed. Capture/record проверки IpCamera с синтетическим RTSP: 2 passed.
- Эти результаты подтверждают доступные локальные/модельные сценарии. Они не заменяют проверку live-камер и Web UI; эти проверки остаются открытыми до отдельного запуска сервиса с корректной конфигурацией доступа.


### Продолжение 2026-10-12: Web UI smoke

- [готово] Штатный `evileye server` запущен на время smoke на порту 8181: `/ready` вернул HTTP 200, `/live` — SPA с HTTP 200.
- [готово] В браузере через временный SSH-туннель отобразилась страница «EvilEye — Операционная консоль» и форма входа. Прямой доступ браузера рабочей станции к 10.245.1.12:8181 заблокирован сетевым маршрутом; через SSH-туннель интерфейс загрузился.
- Авторизованные страницы, камеры и playback этим smoke не проверялись: в credentials.json сохранён только password hash, пароль Web UI не предоставлен. Не использовались значения по умолчанию и не менялись учётные данные.
- Временный backend и SSH-туннель остановлены; порт 8181 закрыт, дочерних процессов сервера не осталось.


### Продолжение 2026-10-12: live RTSP через source SPI

- [готово] В opt-in GStreamer live suite добавлен контрактный сценарий, который запускает встроенный VideoCaptureGStreamer через EvilEyeBase и SourceModuleAdapter, выбирает backend process, получает кадры и записывает сегмент MP4. ffprobe подтверждает, что в файле есть видеопакеты. Smoke прошёл с exit 0; worker после stop штатно завершился, degraded=false.
- [готово] Секреты берутся в памяти из credentials.json, передаются только дочернему тесту через environment и маскируются при выводе ошибок. Обычный запуск файла без live env прошёл: 2 passed, 3 live-теста корректно skipped.
- [готово] Текущая live-проверка кадра прошла для трёх доступных RTSP источников через OpenCV и GStreamer. На одном источнике дополнительно проверена запись в thread и process backend; ffprobe подтвердил содержимое обоих сегментов.
- Остаются авторизованные Web UI проверки и физическое отключение/повторное соединение работающей камеры; последнее нельзя считать безопасным для совместно используемых камер. Переходы reconnect покрыты локальным MediaMTX fixture.


### Продолжение 2026-10-12: агрегация состояния event detector-ов

- [готово] EventsDetectorsController считывает runtime status встроенных и сторонних detector-ов, сохраняет причины по module_id и включает деградировавший worker в общий health status и runtime debug_info. Общее состояние и диагностические счётчики защищены блокировкой, поскольку health status читается вне потока сборщика.
- [проверено] Process detector с намеренно падающим worker-ом не блокирует соседнее правило: тревога от здорового detector-а опубликована, а ошибка первого доступна через runtime stats и debug_info контроллера. Профильные проверки событий и восстановления PostgreSQL: 29 passed.
- [проверено] После реализации агрегации health повторно пройдены все 1 040 unit-тестов и 374 integration-теста с exit 0. После добавления runtime в debug_info полный unit-набор пройден повторно, как и профильные event/PostgreSQL проверки. Условные проверки моделей, real-data, MediaMTX/v4l2loopback и live RTSP пропускаются по указанным в pytest причинам; реальные камеры и source process smoke проверялись отдельным opt-in запуском выше.

### Продолжение 2026-10-12: изоляция импортов spawn-worker и реальная RF-DETR модель

- [готово] Публичные экспорты `evileye.core` и `evileye.object_detector` переведены на ленивую загрузку. Встроенные детекторы по-прежнему регистрируются явно при создании штатных пайплайнов; тесты закрепляют inventory и отсутствие тяжёлых импортов при импорте runtime-контрактов.
- [готово] Проверка реального RF-DETR nano checkpoint из локального `models/rf-detr-nano.pth` прошла через общий `processor_item` в spawn process; smoke проверил DTO результата, отсутствие degraded-состояния и штатную остановку worker-а.
- [готово] Для RF-DETR оставлен только execution mode `process`. Запуск того же пути в thread приводил к нативному abort внутри связки Matplotlib/Supervision при импорте модели; теперь конфигурация thread отклоняется до запуска, а не может завершить весь процесс приложения.
- [проверено] Целевые lazy-import, inventory, registry и detector runtime проверки: 14 passed. Последние полные прогоны: tests/unit — 1 043 теста, tests/integration — 375 тестов, оба с exit 0. Отдельный реальный RF-DETR spawn smoke также завершился с exit 0.

### Продолжение 2026-10-12: burst-проверка очереди тревог

- [проверено] При заблокированном DB worker в очередь размером 8 подан burst из 256 тревог. В очереди осталось ровно 8 принятых сообщений, остальные 248 были синхронно отклонены с явной ошибкой; после восстановления записи принятые сообщения сохранены в FIFO, включая запись, находившуюся в работе.
- Тест закреплён в tests/unit/database_controller/test_alarm_events_db_adapter.py. Новый тест и профильный набор адаптера: 9 passed; полный tests/unit завершился на 100%, а полный tests/integration (375 тестов) прошёл в предыдущем полном прогоне.

### Продолжение 2026-10-12: асинхронная композиция детекторов и backpressure

- [готово] ProcessorStep собирает ответы нескольких совместимых детекторов по source_id, connection_generation и frame_id; быстрый ответ больше не уходит в трекер отдельно, пока остальные назначенные детекторы того же кадра ещё обрабатывают его. Один детектор проходит прежним путём без join.
- [готово] Fanout ограничен очередью ожидания в 512 кадров и тайм-аутом EVILEYE_DETECTOR_FANOUT_TIMEOUT_SEC (по умолчанию 30 секунд). Если модуль завершился без результата, превышен лимит или истёк тайм-аут, доступные результаты передаются дальше, а stage помечается degraded с числом неполных кадров. Незавершённый fanout учитывается в drain конечного источника.
- [проверено] Новый тест внешнего processor_item проходит через конфигурацию PipelineSurveillance в режимах replace/extend и thread/spawn-process. Замедленный второй детектор подтверждает объединение ответов, пришедших в разных вызовах process; отдельная регрессия проверяет timeout, health и drain.
- [готово] Устранён race multiprocessing queue: если после попытки вытеснить старый кадр новый всё ещё не ставится в очередь, входной кадр учитывается как dropped/degraded без исключения из PipelineSurveillance. Старый кадр, если он действительно был вытеснен, отдельно списывается из in-flight/ordered sequence.
- [готово] E2E измеритель теперь ограничивает частоту опроса (--poll-interval-sec, default 1 ms), раз в 250 ms снимает runtime counters и сохраняет health непосредственно до штатного stop, а не после него.
- Проверки на сервере: полный tests/unit прошёл с exit 0; model-backed finite-video PipelineSurveillance E2E — 2 passed (thread и spawn-process); process alarm -> JSON journal API регрессия прошла отдельно. git diff --check чистый.
- Диагностический 10-секундный запуск одного источника из configs/poly-videos-thread.json: source=164, tracker matches=29 (2.85 FPS), p95=861 ms, mean staleness=13.83 кадров; detector dropped=50 и tracker dropped=75, pipeline degraded. Process-конфигурация из configs/poly-videos.json за 10 секунд: source=77, tracker matches=3 (0.18 FPS), p95=8 200 ms, mean staleness=67.33 кадра; detector dropped=33 и tracker dropped=26, pipeline degraded. Активные source/detector/tracker workers были живы в последнем snapshot до stop. Оба профиля явно выявляют перегрузку без исключения или тихой потери. Это диагностические, а не KPI сравнения режимов; worker count, queue capacity и input rate требуют отдельного подбора под целевую нагрузку.
- [проверено] На живом источнике подтверждена композиция встроенных YOLO-модулей и временного стороннего entry point с моделью; результаты guarded smoke приведены ниже.

### Продолжение 2026-10-12: сквозная проверка стороннего fanout на видеоисточнике

- [проверено] Integration-тест запускает реальный `PipelineSurveillance` на конечном MP4: два внешних `processor_item` детектора возвращают `DetectionResultList` с разной задержкой, fanout объединяет результат по каждому исходному ключу кадра и передаёт его встроенному BoT-SORT.
- [проверено] Оба режима — `thread` и `spawn process` — завершились успешно без degraded-состояния. Сценарий покрывает путь VideoCaptureOpencv -> plugin runtime -> detector fanout без весов модели.
- Команда: `QT_QPA_PLATFORM=offscreen python3 -m pytest -q tests/integration/pipeline/test_pipeline_surveillance_plugin_fanout.py` — 2 passed.
- Live-проверка моделей и стороннего пакета выполнена ниже; дальнейшая нагрузочная настройка устойчивого FPS остаётся отдельной задачей.

### Продолжение 2026-10-12: live camera и внешний модельный пакет

- [проверено] Конфигурация запускалась на одном источнике из `configs/poly-cameras.json`, без записи. Два встроенных YOLO-модуля (`yolov8n.pt` и `yolo11n.pt`) в `process` режиме при ограничении до 1 FPS за 20 секунд обработали 19 кадров источника и выдали 19 объединённых результатов; оба worker-а были активны, очереди не теряли элементы, неполных fanout не было, pipeline не degraded.
- [проверено] С теми же двумя встроенными модулями при заданном `desired_fps=5` за 15 секунд получено 48 кадров источника и 46 объединённых detector-результатов; 2 кадра оставались в работе на момент снимка. Сбросов, incomplete fanout и degraded-состояния не было. Фактический входной rate в этом прогоне составил около 3.2 кадра/с; это короткая диагностика, не SLA/KPI.
- [проверено] В отдельном временном каталоге создан внешний Python package с distribution entry point группы `evileye.plugins`. PluginManager обнаружил его без ошибок; два его detector-instance использовали модели YOLOv8/YOLO11 в spawn-процессах на том же источнике при 1 FPS. Из 18 кадров источника 18 объединённых результатов прошли через встроенный BoT-SORT; оба detector-worker-а и tracker-worker оставались активны, drops/incomplete — 0, pipeline не degraded. Репозиторий EvilEye для этой проверки не менялся.
- Первые временные live smoke-скрипты без `if __name__ == "__main__"` исключены из результатов: spawn повторно запускал код проверки в дочерних процессах. Все приведённые выше live-проверки повторены с защищённой точкой входа.
- Короткие измерения подтверждают возможность подключить сторонний пакет и запустить два его модельных модуля через общий runtime. Подбор долговременно устойчивой частоты и отдельные ресурсоёмкие KPI-прогоны остаются открытыми.


### Продолжение 2026-10-12: двухминутная live-проверка fanout под нагрузкой

- Прогон выполнен на сервере на одном источнике `source_id=0` из `configs/poly-cameras.json`; запись отключена. Конфигурация: `desired_fps=5`, два встроенных детектора `yolov8n.pt` и `yolo11n.pt` в `process`, BoT-SORT в `process`. Учётные данные переданы пайплайну тем же `credentials.json`, что использует Controller; значения и адрес камеры в отчёт не включались.
- До активного окна worker-ы подтвердили готовность. После 30 секунд прогрева пайплайн уже был `degraded`: накопилось 41 ожидающее fanout и 32 lifetime incomplete. Поэтому этот замер также показывает, что перегрузка успевает проявиться в коротком прогреве.
- Активное окно составило 120.64 секунды: 850 уникальных source кадров (7.05 FPS), 836 кадров на выходе объединённой стадии детекторов (6.93 FPS) и 244 кадра на выходе трекера (2.02 FPS). После двухсекундного drain у 14 source кадров всё ещё не было detector-результата, а 606 source кадров не имели tracker-результата.
- В активном окне возникло 256 неполных detector fanout; максимум одновременно ожидающих кадров — 68, включая 41 кадр, накопленный до начала окна. Ещё 28 incomplete возникли за двухсекундный drain; после drain ожидающих fanout не осталось. При timeout стадия передавала доступный частичный detector result дальше и отмечала pipeline как degraded.
- За активное окно runtime зарегистрировал `input_queue_dropped`: 130 у YOLOv8, 139 у YOLO11 и 574 у BoT-SORT; `input_queue_rejected` был равен 0. Максимум `in_flight`: 19, 19 и 16 соответственно. Все четыре adapter-а сообщали `worker_running=true` в последнем активном snapshot, но detector, tracker и pipeline оставались degraded.
- Источник настроен с `execution_mode=process`. Его runtime-адаптер отображает `execution_mode=thread`, потому что managed capture backend читается через thread bridge; отдельно `SourceModuleAdapter` сохраняет `backend_execution_mode=process`. Это различие уровней исполнения, а не переключение конфигурации на thread. Для IP-камеры `VideoCaptureOpencv` применяет `FPS_MULTIPLIER_IP_CAMERA=1.5`, поэтому `desired_fps=5` соответствует примерно 7.5 захватываемым кадрам/с; в этом прогоне получено 7.05.
- Вывод: расширяемый fanout и process worker-ы работают на реальной камере, но этот профиль не обеспечивает полную обработку потока. Большая доля кадров не доходит до tracker-а, а detector ensemble часто передаёт частичный результат. Нельзя считать этот режим подходящим для тревог промбезопасности до определения допустимой частоты кадров и явной политики для incomplete fanout.
- Следующая эксплуатационная проверка должна определить устойчивый входной rate на целевом сервере и сопоставить его с `worker_count` детекторов/трекера. Для safety alarm modules политика неполного fanout теперь задаётся через `detector_fanout_policy`: `drop_frame` не передаёт неполный результат следующей стадии, `forward_partial` сохраняет прежнее поведение. Нужно выбрать режим для safety-конфигураций и определить целевой rate; до этого прогон остаётся диагностическим, не SLA/KPI.


### Продолжение 2026-10-12: явная политика неполного detector fanout

- В `PipelineSurveillance` добавлена настройка `detector_fanout_policy`: `forward_partial` — прежнее поведение по умолчанию; `drop_frame` отбрасывает неполный detector result до передачи в tracker.
- Runtime stage statistics теперь включают выбранную политику и `detector_fanout_dropped`; incomplete frame по-прежнему помечает pipeline как degraded. Неизвестное значение отклоняется при инициализации.
- Проверено: прежний partial fanout, новая политика drop и отказ неверной конфигурации. Набор `tests/unit/pipeline` и E2E fanout на конечном видео прошёл после обновления test double в тесте доступа к detector-ам.
- Ограничение: `drop_frame` не означает отсутствие нарушения и не гарантирует генерацию тревоги на отброшенном кадре. Приложение обязано показывать degraded health; требование к частоте кадров и допустимой полноте ensemble остаётся внешним эксплуатационным решением.

### Продолжение 2026-10-12: настраиваемые лимиты detector fanout

- PipelineSurveillance принимает `detector_fanout_timeout_sec` и `detector_fanout_max_pending`; значения проверяются до запуска модулей и передаются в detector stage.
- Runtime health показывает эффективную политику, timeout, лимит ожидания, число ожидающих, incomplete и отброшенных кадров даже до первой ошибки.
- Значения по умолчанию: 30 секунд и 512 кадров. `EVILEYE_DETECTOR_FANOUT_TIMEOUT_SEC` сохранён как legacy источник default timeout; явная настройка pipeline имеет приоритет.


### Продолжение 2026-10-12: runtime diagnostics плагинных модулей

- Контроллер отдаёт через существующий control IPC runtime stats активного pipeline, его plugin-модулей/fanout, обработчика объектов, event detector controller, event processor и event buffers. Ошибки чтения статистики представлены как degraded-компонент с причиной.
- Добавлен GET /api/v1/system/runtime, доступный с правом runtime:view. При остановленном контроллере endpoint возвращает 503 вместо пустого/устаревшего состояния.
- На странице запусков для пользователей с runtime:view показываются общий health badge и раскрываемые подробности модулей/очередей.
- Проверки на сервере: controller control command, его JSON/Unix-socket IPC round-trip и API endpoint — 6 профильных тестов прошли; связанные тесты управления зонами — 3 passed. git diff --check прошёл.
- После добавления диагностики повторены полные suites: tests/unit — 1071 собранный тест, exit 0; tests/integration — 378 собранных тестов, exit 0. Пропуски относятся к opt-in model/real-data и недоступным в окружении MediaMTX, v4l2loopback и live RTSP credentials. После прогонов pytest и worker-процессов не осталось.
- Frontend проверен временным официальным Node.js v24.21.0 (контрольная сумма архива сверена с официальным SHASUMS256.txt): `npm run build` завершился успешно, `tsc --noEmit` и Vite production build прошли. Собранные deployment assets обновлены в `evileye/api/static`.
- Runs UI визуально проверен в браузере через изолированный тестовый сайт и синтетический IPC payload: отображаются degraded health badge и раскрываемые pipeline/module/event diagnostics. Проверка подтверждает отображение, а API и IPC round-trip покрыты отдельными тестами; реальная тревога в журнале браузера отдельно не воспроизводилась. Изолированные процессы, сайт, учётная запись, Node runtime и SSH tunnel после smoke остановлены и удалены; credentials проекта сохранены.

### Уточнение 2026-10-12: частота RTSP потока и стоимость BoT-SORT

Подтверждено отдельным H.265 PTS измерением, что 7.05 FPS источника в прежнем live тесте не были пределом камеры: stream выдавал около 10.06 FPS, а `desired_fps=5` масштабировался для IP камеры в целевой cap около 7.5 FPS. `mc_trackers.enable=false`, поэтому 2.02 FPS — результат per-camera BoT-SORT при включённых `with_reid` и `sparseOptFlow`. Synthetic algorithm ablation показал p50 110 мс для GMC и 65 мс ReID на 10 bbox в 4K; вместе около 172 мс/update. Точные результаты и ограничения приведены в отчёте `reports/tracker_stream_fps_investigation_2026-10-12.md`. Следующий шаг — идентичный replay detector outputs с абляцией ReID/GMC и проверкой качества tracking IDs.
