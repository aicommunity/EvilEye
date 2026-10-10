# План завершения миграции расширяемых модулей EvilEye

## Цель и направление

Довести встроенные компоненты и пайплайны до одного публичного Plugin SPI. Встроенные реализации остаются в репозитории и становятся контрольными примерами для внешних пакетов. `PipelineSurveillance` остаётся специализированным, но расширяемым пайплайном; `PipelineDeclarative` — простым последовательным пайплайном. В первой версии не вводить универсальный DAG, hot-plug и автоматическую установку зависимостей в работающем процессе.

Работы вести на серверной ветке `plugin_support`; текущие серверные изменения не закоммичены. До фиксации миграции каждый этап должен иметь контрактные тесты, диагностику ошибок, запуск штатных конфигураций и подтверждённую остановку процессов.

## Текущее состояние кодовой базы

### Уже реализовано

- `evileye/core/plugins.py` содержит `PluginSpec`, `ModuleSpec`, `PipelineSpec`, `PluginRegistry` и загрузчик entry points группы `evileye.plugins`; есть проверка API version, фабрик, видов модулей, режимов и идентификаторов.
- Встроенные классы регистрируются через `register_module`; старый `EvilEyeBase.register` остаётся совместимым фасадом. Параллельный `EvilEyeBase._registry` удалён.
- `event_registry` использует общий `PluginRegistry`; встроенные и внешние event detectors перечисляются и создаются через него.
- Инвентарь закреплён тестом: 18 встроенных module IDs; отдельный тест явно учитывает девять компонентов с legacy backend-протоколом.
- `PipelineSurveillance` принимает `modules.<group>.mode=extend|replace`, валидирует группы и виды модулей, а `ProcessorFrame` отправляет кадр каждому совместимому процессору. `module_id` принимается наряду со старым `type`.
- `PreprocessingPipeline` и `RoiFeeder` используют `processor_item` runtime.
- Для пользовательских тревог есть `AlarmEvent`: тест проходит от внешнего event detector через controller и JSON adapter до данных журнала; проверены стабильный ID, повторная доставка, retry временной ошибки и диагностика переполнения очереди.
- Порядок штатного завершения API приведён к остановке ConfigRunManager и PipelineManager до закрытия Unix frame relay. Добавлена регрессия на порядок остановки.
- Исправлены выявленные тестами дефекты: проверка `track_id` с ключом `(source_id, track_id)`, синхронизация health process capture, обход нестабильной индексации Ultralytics Boxes в smoke test, ожидание асинхронного результата BoT-SORT и обнаружение записей в нескольких уровнях каталогов.

### Что пока остаётся legacy или отдельной реализацией

- Девять модулей ещё имеют capabilities `legacy_*_protocol` и создаются соответствующими адаптерами:
  - источники: `VideoCaptureOpencv`, `VideoCaptureGStreamer`;
  - детекторы: `ObjectDetectorYolo`, `ObjectDetectorYoloMp`, `ObjectDetectorRtdetr`, `ObjectDetectorRfdetr`;
  - tracker: `ObjectTrackingBotsort`;
  - атрибуты: `AttributeDetector`, `AttributeClassifier`.
- `ObjectMultiCameraTracking` — синхронная batch-стадия; общего batch SPI нет, она остаётся thread-only.
- Event detectors уже видны через SPI, но их lifecycle и подписки на `ObjectsHandler` задаёт отдельный `EventsService`; для них ещё нет общего runtime/health-контракта.
- В `PluginRegistry` есть API пайплайнов и стороннего discovery, но встроенные классы пока не декларируют `PipelineSpec` через `register_pipeline` (в коде нет вызовов регистрации встроенных pipeline manifests). `PipelineService`/service locator и PluginRegistry поэтому ещё не дают одного пути разрешения встроенных пайплайнов.
- Есть unit-проверки entry point и custom alarm detector, но пока нет отдельного устанавливаемого стороннего wheel/editable-пакета, проверенного с чистого окружения EvilEye.

## План оставшихся доработок

### Этап A. Уточнить контракт runtime и диагностику

1. Зафиксировать публичные протоколы `processor_item`, `source`, `event_detector` и `batch_processor` в небольших интерфейсах/документации: создание из config, `init/start/stop`, health, сообщения об ошибках и состояние деградации.
2. Подключить `ModuleSpec.config_schema` к проверке конфигурации до старта фабрики; ошибки должны содержать qualified module ID и путь к неверному полю.
3. Для `batch_processor` добавить отдельный kind/capability с явной потоковой семантикой; до готовности multiprocessing оставить для него только `thread`.
4. Определить правила исполнения `process`: spawn-safe фабрика, сериализуемые входы/выходы и state внутри worker; при несовместимости режима останавливать конфигурацию до старта.
5. Для очередей определить поведение по виду данных: кадры могут иметь ограниченную политику drop-oldest, тревоги должны сообщать о переполнении и ошибке сохранения.

**Проверки:** контрактные тесты создания, старта, остановки, ошибки init, исключения `process_item`, переполнения очереди, сериализации, отказа неподдерживаемого execution mode и schema errors.

### Этап B. Удалить legacy processor adapter по семействам

1. Перевести YOLO, YOLO-MP, RT-DETR и RF-DETR на общий item runtime: вход `Frame`/DTO, собственное состояние worker, унифицированный выход detections/debug metadata. Сохранить текущие backend реализации и параметры модели.
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

1. Перенести `ObjectMultiCameraTracking` на batch SPI с явными требованиями к синхронизации и `thread`-ограничению.
2. Перевести Event detector фабрики и lifecycle с `EventsService` на PluginRegistry + общий runtime; оставить `EventsService` как управляющий слой, не второй реестр.
3. Довести `AlarmEvent` до общего контракта: type, severity, timestamp, source, details, stable ID. Проверить JSON и PostgreSQL adapters, повтор записи, недоступное хранилище и журнал UI.
4. Добавить диагностируемую остановку/переполнение, retry с ограничением и метрики очереди; отдельно решить долговечный outbox, если нужна гарантия пережить падение хоста (сейчас такой гарантии нет).

**Критерий:** внешний event/alarm detector не меняет ядро для нового события и проходит до выбранного хранилища и общего представления в журнале.

### Этап E. Свести пайплайны к реестру и проверить внешний пакет

1. Зарегистрировать `PipelineSurveillance` и `PipelineDeclarative` как встроенные `PipelineSpec`; перевести `PipelineService` на единое разрешение через PluginRegistry.
2. Сохранить `pipeline_class` только как compatibility alias. Если выбранный pipeline неизвестен или контракт не проходит, завершать запуск с понятной диагностикой, не делать fallback.
3. Оставить `PipelineSurveillance` фиксированным графом стадий, документировать порядок, правила `extend`/`replace`, несколько детекторов на один источник и thread-only стадии.
4. Подготовить минимальный пример стороннего пакета и проверить editable install/entry point из чистого server-side virtualenv без изменения исходников/переустановки EvilEye.
5. Проверить конфликт ID, неизвестный module/pipeline, неверную API version, ошибку импорта и требования зависимостей.

**Критерий:** builtin и внешний pipeline разрешаются тем же API; сторонний package обнаруживается после перезапуска приложения.

### Этап F. Полный regression и эксплуатационная проверка

1. Запускать `tests/unit`, затем интеграционные группы последовательно; после каждой проверки убеждаться, что дочерние multiprocessing workers завершились.
2. Обеспечить headless режим Qt тестов: при отсутствии `DISPLAY`/`WAYLAND_DISPLAY` использовать `QT_QPA_PLATFORM=offscreen`.
3. Проверить штатный видеофайл с детекцией/трекером, запись сегментов и остановку; провести отдельный запуск с RTSP камерами, не выводя URL и пароли в логи аудита.
4. Проверить Web UI и API: публичную загрузку, доступные экраны после входа и просмотр live/recorded video. Для защищённых маршрутов нужны валидные пользовательские учётные данные.
5. Снять финальный инвентарь legacy capabilities и считать миграцию завершённой только при нуле legacy протоколов либо с документированным, владельцем согласованным исключением.

## Проверки на сервере 2026-10-10

- `tests/unit`: полный набор завершился с `UNIT_EXIT=0`; дополнительный smoke-тест подтвердил создание Configurer при уже установленном multiprocessing `spawn`.
- `tests/integration`: `311 passed, 42 skipped`; пропуски связаны с отсутствием локального RTSP тест-сервера, тестовой RTSP переменной/пароля, v4l2loopback и выключенными real-data тестами. После итогового summary pytest оставил один multiprocessing worker и не завершил процесс сам; тестовый процесс был остановлен. Причину worker leak ещё нужно локализовать и исправить.
- Полный API/system запуск с видеофайлом успешен: `PipelineSurveillance`, capture process, YOLO и BoT-SORT стартовали; видео переподключалось в loop; позже `MemoryAttr` показал активный объект; приложение остановлено с кодом 0. При shutdown больше не было `Frame relay publish failed` и ошибок ack от остановленного capture worker.
- В scratch-каталоге есть 18 MP4 сегментов, суммарно около 84 MB; `ffprobe` прочитал первый сегмент: 4.97 секунды, MPEG-4, 3840×2160.
- Проверка трёх камер из `configs/vehicle_perpocessing.json`: TCP endpoints доступны, но конфигурация не задаёт пароли; прямой RTSP DESCRIBE возвращает `401 Unauthorized`. Камеры нельзя считать проверенными по видео до предоставления корректных camera credentials/конфигурации. Секреты в документацию не копировались.
- Web UI загрузился через tunnel и показал «Вход в веб-интерфейс». Корень возвращал HTTP 200; `/api/v1/health` и `/api/v1/state` — 401. Без учетной записи пройти защищённые сценарии и проверить кадр/журнал через UI не удалось.

## Условие завершения миграции

Миграция завершена, когда встроенный inventory целиком работает через Plugin SPI, legacy protocol count равен нулю (кроме явно принятого исключения), builtin и внешний пакет проходят одинаковые контрактные тесты, полный доступный suite завершается без оставшихся процессов, штатные видео и тревоги проходят end-to-end, а внешние ограничения камер и Web UI закрыты корректной конфигурацией доступа.
