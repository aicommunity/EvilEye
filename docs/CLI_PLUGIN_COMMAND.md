# Команда evileye plugin

Команда создаёт отдельный Python-пакет расширения, который EvilEye находит
через entry point группы evileye.plugins. Поэтому команда называется plugin:
пакет является единицей установки и обнаружения, а модуль или pipeline —
объявленным в нём компонентом.

## Команды

В терминале `evileye plugin` открывает меню группы. Если запустить
`evileye plugin create` без имени, CLI спросит имя пакета и предложит выбрать
шаблон и каталог. Вызов с явным именем остаётся обычной командой и не задаёт
дополнительных вопросов:

Список шаблонов:

    evileye plugin templates

Создание пакета в текущем каталоге:

    evileye plugin create site-safety

Выбор шаблона и каталога-родителя:

    evileye plugin create site-safety --template alarm --output-dir ./plugins

Создание не перезаписывает существующую папку. Имя должно начинаться с
латинской буквы и содержать строчные латинские буквы, цифры, дефисы или
подчёркивания. Дефисы нормализуются в подчёркивания для Python package и
plugin_id.

## Шаблоны

| Шаблон | Контракт | Начальное содержимое |
| --- | --- | --- |
| processor | processor_item | Преобразует mapping или пару data/frame, добавляя метку |
| detector | processor_item | Возвращает пустой DetectionResultList и сохраняет frame; место для inference отмечено TODO |
| alarm | event_detector | PPE-правило выдаёт AlarmEvent при входе в состояние нарушения |
| source | source | Синтетический конечный источник чёрных BGR кадров для проверки жизненного цикла |
| pipeline | PipelineSpec | Минимальный PipelineBase с start/process/stop и фабрикой от PipelineDependencies |

Первые три шаблона показывают всё более предметные варианты обработки кадра
и событий. Источник и собственный pipeline создают отдельные точки расширения.
Заглушка detector не содержит модели и намеренно не заявляет, что обнаруживает
объекты до добавления пользователем inference-кода.

## После создания

Перейдите в каталог пакета и установите его editable в то же Python-окружение,
которым запускается EvilEye:

    cd plugins/site-safety
    python -m pip install --upgrade pip setuptools
    python -m pip install -e .

Перезапустите EvilEye. После запуска плагин появится в реестре под namespace,
к примеру site_safety/example_alarm. Код плагинов не сканируется прямо из
произвольных каталогов и не перечитывается в уже работающем процессе.

Для alarm-шаблона добавьте site_safety/example_alarm в events_detectors.enabled.
Если там уже перечислены встроенные детекторы, сохраните их в списке.
Шаблоны processor и detector подключаются к поддерживаемой группе в
PipelineSurveillance через modules.<group>.items с полем module_id. Для
детектора группы можно использовать режим extend, чтобы оставить встроенные
детекторы. Собственный pipeline выбирается через pipeline_class.

Смотрите полный контракт и форматы конфигурации в PLUGINS.md. Python-плагин
получает права процесса EvilEye; запуск в process режиме не является
песочницей.
