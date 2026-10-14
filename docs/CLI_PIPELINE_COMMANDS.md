# Просмотр и настройка pipeline из CLI

Команды рассчитаны на локальную и SSH-консоль. Просмотр и форма не запускают
pipeline, камеры, модели или worker-процессы: для описания графа читается JSON,
а для живого состояния — уже опубликованный runtime snapshot.

## Топология и состояние

```bash
evileye pipeline inspect configs/system.json
evileye pipeline inspect configs/system.json --format edges
evileye pipeline inspect configs/system.json --format dot > pipeline.dot
evileye pipeline inspect configs/system.json --format json > pipeline.json
```

`tree` показывает стадии и порядок модулей; `edges` — направленные связи,
включая fan-out; `dot` выдаёт Graphviz DOT в stdout и не требует Graphviz;
`json` выдаёт машиночитаемое описание без значений конфигурации и реквизитов
камер. Для визуального файла DOT можно обработать отдельно:

```bash
dot -Tsvg pipeline.dot -o pipeline.svg
```

Если конфигурацию можно однозначно разрешить по текущему site-профилю, путь
можно опустить. В противном случае укажите `CONFIG`. Для состояния уже
запущенного экземпляра используйте его ID со страницы запусков или из
`evileye pipeline status`:

```bash
evileye pipeline inspect --run 42
evileye pipeline inspect --run 42 --format json
evileye pipeline inspect --run 42 --watch
```

`--run` читает runtime snapshot и обновлённое состояние процесса. В `tree` и
`edges` узлы помечаются `running`, `degraded`, `unknown` или `stale`. Старый
snapshot без per-module telemetry, отсутствие статистики и устаревшие данные
не отображаются как здоровое состояние. Все форматы явно показывают свежесть
телеметрии (`fresh`, `stale`, `unknown`) и её возраст, если время публикации известно.
`--watch` обновляет только терминальный
вид `tree` или `edges`; остановите его через Ctrl-C. Он не подключается к
pipeline для горячего управления.
При остановке запуска или исчезновении snapshot обновление завершается с диагностикой.

## Реестр модулей

```bash
evileye plugin list
evileye plugin list --kind processor_item
evileye plugin list --kind event_detector
```

Вывод содержит ID, видимое имя, допустимые стадии, режимы исполнения и наличие
схемы формы. Допустимые значения `--kind` доступны как публичный набор
`MODULE_KINDS` в `evileye.core.plugins`.
Встроенные детекторы, трекеры и обработчики кадров имеют общий вид
`processor_item`; их назначение различается по перечисленным стадиям.

## Мастер настройки

```bash
evileye pipeline configure configs/system.json
evileye pipeline configure
ssh -t user@host 'cd ~/EvilEyeDeploy && evileye pipeline configure configs/system.json'
```

Мастер работает в TTY: выбирает pipeline и стадии, позволяет добавлять,
удалять, переставлять и настраивать модули. Для `PipelineSurveillance` доступны
его фиксированные группы; для `PipelineDeclarative` — список линейных стадий.
Для встроенного surveillance pipeline отдельно настраиваются параметры
fan-out детекторов; конфигурация стадий остаётся в мастере модулей.
`PipelineCapture` использует только первый файловый источник OpenCV; мастер
предлагает для него соответствующий модуль. Для declarative pipeline можно
выбрать стадию результата через `final_results`.
При создании нового файла мастер предлагает встроенные и сторонние pipeline.
Сторонний модуль доступен в форме, если объявил схему конфигурации и совместимую
стадию. Поля, которых нет в схеме, сохраняются; неизвестный модуль можно оставить
в конфигурации и настроить вручную.

Например, для добавления детектора выберите «Детекторы объектов» → «Добавить
модуль», затем модуль из реестра. В форме задайте `source_ids` как JSON-массив
(например, `[0]`), `model`, порог `conf` и поддерживаемый `execution_mode`.
Выберите «Готово», вернитесь из списка модулей и завершите настройку стадий.
Проверьте diff перед ответом `y` на запрос сохранения. Настройка сохраняет
конфиг; применяйте его при следующем запуске или штатном перезапуске pipeline.

После редактирования CLI проверяет известные схемы, показывает diff и просит
подтверждение с ответом по умолчанию «нет». Секреты и userinfo URL скрываются в
diff. До подтверждения исходный файл не меняется. При сохранении запись
выполняется атомарно, предыдущая версия сохраняется рядом как
`<имя>.bak.<UTC timestamp>`, остаются последние 10 копий. Неизменённый файл не
перезаписывается и резервная копия не создаётся.

Без интерактивного терминала `configure` завершается понятной ошибкой и не
создаёт файл. Для скрипта проверяйте конфигурацию вручную или используйте
неинтерактивные команды `pipeline inspect` и JSON-редактор.

## Разработчикам плагинов

`ModuleSpec` принимает отображаемое имя, описание, `config_schema`, перечень
`stages`. Для схемы формы подойдёт JSON Schema-совместимый словарь, Pydantic
модель либо объект с `model_json_schema()`/`schema()`. Валидатор может быть
callable, но без описания JSON Schema он не показывается как интерактивная
форма. Встроенные модули перечисляют поля, включая legacy-конфигурацию; лишние
поля сохраняются.
Схемы поддерживают типы, enum, nullable, вложенные объекты и массивы,
`required`, `additionalProperties` и числовые/строковые ограничения. Объявленные
значения `default` показываются с пометкой, а незаданные значения — как
«Не задано в конфигурации». Поля с `secret: true` или `writeOnly: true`
маскируются как пароль, не очищают сохранённое значение при пустом вводе.
Необязательный `ui_schema` в `ModuleSpec` и `PipelineSpec` задаёт порядок полей
и подсказки интерфейсу; он не меняет контракт или валидацию.
Схема описывает параметры фабрики. `module_id`, `execution_mode`, `source_ids`
и другие служебные поля исполнения проверяются отдельно; они не требуют
разрешения в строгой схеме с `additionalProperties: false`. Мастер сам
предлагает режим исполнения и привязку источников. Если параметры уже
хранятся во вложенном `config`, форма редактирует их внутри этого объекта.

Пример метаданных стороннего обработчика:

```python
ModuleSpec(
    module_id="rule",
    kind="processor_item",
    factory=Rule,
    execution_modes=("thread", "process"),
    display_name="Safety rule",
    description="Checks each frame for a safety violation.",
    stages=("detectors",),
    config_schema={
        "type": "object",
        "properties": {
            "threshold": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.5},
        },
        "additionalProperties": False,
    },
)
```

`PipelineSpec` может объявить `display_name`, `description`, `config_schema` и
`topology_provider(config)`. Provider возвращает
`evileye.core.pipeline_topology.PipelineTopology`; без него pipeline
отображается как один непрозрачный узел с пояснением. Объявление topology —
только описание, оно не меняет runtime-граф и не загружает компоненты на лету.

Подробности регистрации и установки пакета: [PLUGINS.md](PLUGINS.md) и
[CLI_PLUGIN_COMMAND.md](CLI_PLUGIN_COMMAND.md).
