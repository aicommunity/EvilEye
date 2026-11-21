# Конструктор пайплайнов и плагинов Web UI

## Русский

В `/admin/extensions` доступен отдельный административный режим. Он требует
активную сессию пользователя с точной ролью `admin`; одного разрешения
`system:admin` при другой роли недостаточно. API режима находится под
`/api/v1/admin/extensions/*` и проверяет роль повторно на каждом запросе.

По умолчанию режим разрешён только с localhost. Сервер определяет адрес через
общий резолвер EvilEye: `X-Forwarded-For` учитывается только если непосредственный
клиент является настроенным доверенным proxy. Неизвестный или некорректный адрес
отклоняется. Для управляемого внешнего доступа оператор может задать
`EVILEYE_BUILDER_LOCALHOST_ONLY=0`; после изменения переменной перезапустите Web
backend.

### Редактор пайплайнов

Режим поддерживает формы `PipelineSurveillance`, `PipelineDeclarative` и
`PipelineCapture`. Каталог берётся из того же plugin registry, который
используют приложение и CLI. Схема пайплайна показана обзорным графом: узел
можно выбрать, но нельзя перетаскивать или соединять произвольным образом,
поскольку порядок задаётся контрактом пайплайна. Ниже редактор показывает
стадии и список модулей выбранной стадии, а параметры выбранного модуля — в
отдельном инспекторе. В графе кликом можно перейти к стадии и модулю.

Для Surveillance можно добавлять, удалять и переставлять модули в группах,
выбирать `extend` или `replace`, менять режим исполнения и назначать детекторы
на выбранные источники из списка камер. Параметры стадий переключаются вкладками;
стрелки, Home и End переключают их с клавиатуры. Встроенная ветка событий
показывает правила, включённые по умолчанию; пользовательские правила можно
добавлять, не отключая встроенные. Declarative редактирует одну выбранную
стадию за раз, а Capture ограничивает список одним видеозахватом.

Поля из JSON Schema отображаются обычными контролами: вложенные объекты —
группами, массивы — списками с управлением порядком, массивы объектов —
раскрываемыми элементами, словари — редактируемыми свойствами. Если значение
объявлено как `default`, интерфейс помечает его как значение схемы; незаданные
поля явно помечаются как незаданные. Секретные поля маскируются и не очищают
сохранённый секрет при пустом вводе. Пользовательский `ui_schema` может задать
порядок полей и виджеты, но не меняет серверную проверку. Для неизвестных форм
оставлен JSON-режим.

Declarative editor меняет имена, типы, порядок стадий и их модули. `PipelineCapture`
настраивает единственный поддерживаемый видеозахват. Остальные зарегистрированные
пайплайны доступны в форме, если автор объявил схему; без схемы конфигурацию можно
править как JSON. Неизвестные поля сохраняются.

Проверка показывает топологию из конфигурации и ошибки схемы; она не запускает
пайплайн и не открывает камеры. Перед записью показывается обзор изменений с
маскированием чувствительных значений. Сохранение выполняется атомарно в
`<site>/configs`, делает резервную копию и хранит последние 10 копий. Запуск или
перезапуск пайплайна после сохранения пользователь выполняет отдельно.

### Создание плагина

На вкладке «Плагины» выберите имя пакета и шаблон `processor`, `detector`,
`alarm`, `source` или `pipeline`. Web UI создаёт пакет в
`<site>/plugins/<имя>`, формирует ZIP и запускает editable-установку в Python
окружение EvilEye. Отслеживаемая операция сохраняется под
`<site>/plugins/.evileye/operations`, поэтому её состояние можно запросить после
перезапуска backend. При повторном открытии вкладки можно выбрать одну из
последних операций и скачать её ZIP.

Зависимости проекта не устанавливаются автоматически. Если их нет, пакет
остаётся на диске, а интерфейс показывает список зависимостей. При наличии
управляемого системного сервиса с тем же Python EvilEye планирует его перезапуск и
проверяет готовность Web UI. В ручном запуске и контейнере пакет устанавливается,
а операция получает статус `pending_restart`; перезапустите сервис либо контейнер
внешним для Web UI способом. Работающие pipeline-процессы автоматически не
перезапускаются.

Генератор и валидатор используют общий Python-код вместе с CLI:

```bash
evileye plugin list
evileye plugin create site-safety --template alarm --output-dir ./plugins --zip
evileye pipeline inspect configs/system.json --format tree
evileye pipeline configure configs/system.json
```

Основные API:

- `GET /api/v1/admin/extensions/catalog`
- `POST /api/v1/admin/extensions/preview`
- `POST /api/v1/admin/extensions/configs`
- `POST /api/v1/admin/extensions/plugins`
- `GET /api/v1/admin/extensions/operations`
- `GET /api/v1/admin/extensions/operations/{id}`
- `GET /api/v1/admin/extensions/operations/{id}/archive`

## English

The dedicated administration workspace is available at `/admin/extensions`.
Every page operation requires an authenticated user whose exact role is `admin`;
the API repeats this check for every request. The endpoints live under
`/api/v1/admin/extensions/*`.

The workspace is restricted to localhost by default. Client addresses are resolved
with EvilEye's trusted-proxy resolver. Forwarded headers are accepted only from a
configured trusted proxy, and unknown addresses are rejected. An operator can
disable the restriction with `EVILEYE_BUILDER_LOCALHOST_ONLY=0`; restart the Web
backend after changing the setting.

The builder supports `PipelineSurveillance`, `PipelineDeclarative`, and
`PipelineCapture`. A read-only topology graph selects a stage or module; it does
not allow dragging nodes or creating connections because stage order follows the
pipeline contract. The selected stage shows a compact module list and one module
inspector. Surveillance groups support module selection, ordering, source
assignment, and `extend`/`replace`; its event branch keeps built-in default rules
enabled when a custom rule is added. Declarative exposes one selected stage at a
time, and Capture limits the source list to one capture module. Other pipelines are
form-editable when their plugin declares a schema, and remain available in the JSON
editor otherwise. Unknown fields are preserved.

JSON Schema fields render as controls, grouped objects, editable arrays, collapsible
arrays of objects, and editable dictionary properties. Declared defaults are
identified as schema defaults; fields absent from the configuration are marked as
unset. Secret fields remain password-masked and an empty edit preserves the saved
secret. An optional RJSF `ui_schema` controls field order and widgets without
changing server-side validation. Unknown forms retain the JSON editor.

Preview validates the configuration and displays its declared topology without
starting a pipeline or opening cameras. A redacted change review appears before an
atomic save. The previous config is backed up and only the latest 10 copies are
retained. Saving never starts or restarts a pipeline.

Plugin creation generates a package under `<site>/plugins/<name>` and a matching
ZIP, then installs the package editable into the EvilEye Python environment. The
operation record is stored under `<site>/plugins/.evileye/operations` and remains
queryable after a Web backend restart. Reopening the tab restores recent operations
so their status and ZIP can still be inspected. Plugin dependencies are never installed
automatically. Missing requirements are reported while the generated package and
ZIP remain available. A managed service using the same Python interpreter is
restarted automatically when possible; manual and container deployments report
`pending_restart`. Running pipeline processes are not restarted.
