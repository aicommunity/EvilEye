# Проверка исправлений повторного аудита EvilEye

Дата: 23.09.2026. Проверенный код: **`dcfc98dd0247a651ea8135a861d87378ddb5089e`**, ветка `14-hotfix`.

Основание: [повторный аудит и задачи R01–R17 / T01–T19](PROJECT_REAUDIT_32acaa52.md), опубликованные в `4d7408f54aac4c789f35c57980caada86e12b77c`. Проверены все **15 последующих коммитов**, изменения в 93 файлах (+1783/−329 с распознаванием переименований), связанные маршруты, storage, authentication и frontend lifecycle. [Точный диапазон](audit_dcfc98dd/revision_range.json).

## 1. Вывод

**Принимать весь план как выполненный пока нельзя.** Существенная часть исправлений полезна, но несколько требований реализованы только в helper-функциях, без проверки полного пути запроса. Найдены новые функциональные регрессии и незакрытые условия приёмки предыдущего аудита.

Самый серьёзный пропуск — **отзыв серверной сессии**: отключённый пользователь продолжает читать видео с прежней cookie, а пониженный администратор сохраняет административные права. Это подтверждено HTTP-запросами после изменения пользователя через настоящий `/users` API.

Новые регрессии, непосредственно влияющие на работу UI:

- обычные object previews возвращают 403 даже администратору;
- Live WebSocket закрывается с 4403 при первой подписке пользователя с неограниченным доступом;
- notify одной камеры отменяет загрузку JPEG другой камеры того же run;
- фоновая загрузка детекций отменяет сама себя и оставляет `backgroundLoading=true`;
- исправленный round-robin фактически продолжает начинать обход metadata с первой камеры.

Смена auth epoch очищает часть кэшей, но не изолирует все данные и незавершённые запросы. После очистки может вернуться старый кадр, metadata store передаёт данные прежней подписки, а строки журнала остаются видимыми при изменении прав того же пользователя.

**Приоритет:** сначала F01–F07, затем корректность индексов и управления работой F08–F11. Приёмочные тесты F12 нужны одновременно с исправлениями. Оценку быстродействия и дальнейший рефакторинг проводить после функциональных исправлений.

## 2. Методика и ограничения

Использованы diff всех 15 коммитов, чтение текущих реализаций и их вызывающего кода, штатные тесты, отдельные воспроизведения HTTP/concurrency и настоящих React effects.

| Проверка | Результат |
|---|---|
| `tests/unit/api`, meta exit-status, journal resolver, journal integration smoke | **368 tests: 354 passed, 14 failed**, 222.124 с |
| Штатный frontend Vitest | **24 файла, 180 tests passed** |
| TypeScript `--noEmit` | Успешно |
| Vite build в отдельную временную папку | Успешно; все 34 JS/CSS-файла совпадают с Git blobs текущего SHA |
| Отдельные backend probes | Подтверждены HTTP-дефекты, ошибка WS-маршрута и две ошибки индексов |
| Отдельные React/store probes | **6 из 6 воспроизведений подтвердили дефекты** |

`index.html` сборки отличается от сохранённого только форматированием; несовпадения JS/CSS, объясняющего найденные ошибки старой SPA, нет. Полный перечень проверок, версий и failures: [validation_summary.json](audit_dcfc98dd/validation_summary.json).

HTTP-проверки используют synthetic users, media и временный data root. WS-проверка исполняет настоящий маршрут, но заменяет handshake, discovery run и внешний источник ACL. React-проверки исполняют настоящие hooks/stores через React 18.3.1; сеть, WebSocket, URL blobs и часы контролируются тестом. Это проверка lifecycle, **не браузерное измерение FPS/TTI**.

Не выполнялись новые измерения на production/Linux, реальная видеозапись, GPU-нагрузка, полный Qt/БД/capture suite, браузерный Performance/Profiler и длительный soak. Числа из существующего Linux perf-отчёта ниже рассматриваются как предоставленные артефакты, а не как повторённый здесь эксперимент. Состояние удалённого CI не проверялось.

Код приложения в рамках этой проверки не изменялся. Скрипты в `audit_dcfc98dd` — доказательства наблюдаемого поведения: **их успешное завершение означает воспроизведение ошибок**, а не готовность релиза. После исправлений ожидания следует инвертировать и перенести в штатные tests.

## 3. Что действительно улучшилось

- Media ACL теперь проверяет canonical path и тип файла. Старый HTTP-обход `Cam2/../Cam9` возвращает 403; прямой доступ к разрешённому видео остаётся 200.
- Events singleflight возвращает общий список, пользовательская проекция вынесена после ожидания; endpoint дополнительно фильтрует результат. Прежний конкретный дефект events устранён по коду и новым тестам.
- Detection builder при изменении source version пересчитывает уже известные камеры; версия индекса увеличена. Это устраняет механизм закрепления старого содержимого R04, но не гонку разных callers F08.
- Event builder использует `presentation_cap=None`; прежнее ограничение 2000 больше не применяется к внутренней сборке. Условия coverage всё ещё неполны, см. F09.
- Playback cache разделяет fresh/stale сроки, fresh miss сохраняет stale, хранит размер entry, отклоняет oversized entry. Это реальное улучшение R06/R15.
- State helper включает ожидание semaphore в deadline; реальные state routes его используют.
- Hub очищает pending при смене подписки и проверяет актуальный source set перед отправкой; PATCH пользователя закрывает его preview clients.
- Live visibility различает «ещё не определена» и «ничего не видно»; изменение набора run больше не делает общий cleanup всех соединений. Blob и ETag обновляются вместе.
- В journal load/reload объединены внешний abort и timeout; stale catch защищён generation/epoch. Добавлены auth scope, ключи с epoch, контракты и часть regression tests.

Эти результаты не отменяются найденными ниже дефектами. Нужна доработка границ между механизмами, а не возврат к предыдущей реализации.

## 4. Реестр пропущенных проблем

| ID | Приоритет | Проблема | Основание | Связь с прежним планом |
|---|---|---|---|---|
| F01 | P0 | Отключение/понижение пользователя не отзывает старую HTTP-сессию | HTTP | Пропуск authentication; T06 шире исправления preview hub |
| F02 | P1 | ACL ломает легитимные journal images и камеры с дефисом | HTTP + writer | Регрессия T04 |
| F03 | P1 | Unrestricted Live WS закрывается на subscribe/ping | Настоящий маршрут с fake transport | Регрессия T06 |
| F04 | P1 | Notify cancellation общая на run вместо камеры | Настоящий hook | Регрессия T13 |
| F05 | P1 | Background detection effect отменяет собственную загрузку | Настоящий hook | Регрессия T15 |
| F06 | P1 | Auth epoch не ограждает stores, текущие rows и late responses | Hooks/store + код | T07 не завершён |
| F07 | P2 | Metadata round-robin не продвигает cursor | Настоящий store + fake timers | T14 не закрыт |
| F08 | P1 | Detection singleflight разделяет проекцию лидера | Два потока, настоящий SingleFlight | Остаток T05/R03 |
| F09 | P2 | Coverage пустых event-камер теряется при следующей сборке | Четыре вызова builder | Остаток T09/R05 |
| F10 | P1 | Playback deadline и очередь не соответствуют общему контракту; stale может стать fresh | Код вызывающих routes | T10/T11 частично |
| F11 | P1 | Нет общего ограничения памяти всех caches и стоимости работы event loop | Код; без RSS-профиля | T12/R15 частично |
| F12 | P1 | Зелёные локальные helper tests не обеспечивают release gate | Запуск тестов + CI script | T01–T03 частично |
| F13 | P2 | Perf-артефакты не доказывают устранение UI lag | Разбор script/JSON/report | T17/T18 не приняты |

### F01. Старая cookie сохраняет отозванные права

**Места:** `evileye/api/security.py:203`, `core/camera_access.py:45`, `app.py:80`, `routes/realtime.py:103`, `routes/users.py:255`.

`current_user()` доверяет user/role из подписанной session cookie и выводит permissions из этой роли. Он не сопоставляет её с текущим существованием, `disabled`, статусом и ролью пользователя. `resolve_camera_access()` читает актуальную запись для camera preferences, но admin bypass выбирает по роли из session. Проверка нового login и проверка существующей сессии поэтому расходятся.

**HTTP-воспроизведение:**

| Последовательность | Наблюдение |
|---|---|
| ops login → admin PATCH `disabled=true` → ops старая cookie GET разрешённого видео | **200** |
| Тот же ops, новый login после отключения | **401** |
| secondadmin login → admin PATCH `role=user`, ACL только Cam2 → старая cookie GET `/users` | **200** |
| Тот же пониженный пользователь GET видео Cam9 | **200** |

Закрытие preview clients по username не отзывает signed cookie и не устраняет REST-проблему. На WS-пути role также читается из session; отсутствует единая актуальная проверка disabled/status. Metadata WS и MJPEG не получают общего механизма отзыва. После исправления F03 этот пробел нельзя оставить за маской закрывающегося WS.

**Исправление:** единый resolver актуального principal для HTTP и всех transport; revision/revocation session, проверка disabled/deleted/rejected/role. Определить момент прекращения уже открытого stream. Не ограничиваться очисткой frontend или очередным kick preview hub.

**Приёмка:** реальные login/cookies → disable, demote, delete, reject, camera revoke; старые и новые HTTP-запросы, WS reconnect и уже открытые WS/MJPEG не сохраняют прежние права. В тестах должны быть как credentials users, так и web user store.

### F02. Canonical media resolver не моделирует текущий формат архива

**Места:** `core/media_access.py:20,50,102,123`, `routes/journals.py` (`_authorize_journal_media`), `evileye/objects_handler/objects_handler.py:1092`.

Allowlist разрешает только `Streams`/`Events`. Текущий writer сохраняет object images под `Detections/<date>/Images/FoundPreviews|FoundFrames|Lost…`. Проверка root идёт до unrestricted bypass — обычный object preview получает 403 даже для admin. Для event images под `Events/<date>/Images/...` parser не определяет владельца и отклоняет restricted user. Называть все такие изображения «legacy» в `docs/reaudit_contracts.md` неверно: этот layout создаёт актуальный writer.

Отдельно, `folder.split('-')` превращает разрешённую камеру `Cam-2` в composite `Cam`+`2`. Probe: admin video 200, пользователь с `allowed_cameras=['Cam2','Cam-2']` — 403 для Cam-2.

**Исправление:** связать canonical file с владельцами через запись журнала/manifest/storage contract для всех реальных layouts; учесть основной и configured root, preview/frame/video и composite. Не разрешать все ownerless images ради устранения 403. Согласовать resolver с writer, а не только с синтетическим деревом `Streams`.

**Приёмка:** полная положительная и отрицательная HTTP-матрица для реальных writer paths. Разрешённые preview/frame работают для admin и restricted; чужие, JSON, traversal и symlink не расширяют доступ; дефис в имени камеры не меняет владельца. Уже падающие journal smoke/preview tests должны стать зелёными без ослабления ACL.

### F03. `None` одновременно означает полный доступ и отказ

**Места:** `routes/realtime.py:337–369`, `core/camera_access.py:392`.

`allowed_source_ids_for_run()` возвращает `None` для unrestricted. Новый `_refresh_allowed()` использует тот же `None` для запрета, а receive loop закрывает WS при любом `None`. Начальная проверка пропускает admin/auth-disabled, `accept()` выполняется, первая подписка закрывает соединение с 4403. Это воспроизведено с настоящим receive loop.

**Исправление:** разные типы/состояния для unrestricted, restricted-empty и разрешённого множества; один контракт на handshake, subscribe и ping. Для unrestricted ping также нельзя выполнять `sid in None` после локального снятия close-ветки.

**Приёмка:** маршрут целиком: admin, auth disabled, restricted nonempty, empty ACL; subscribe→ping→ACL change. Проверки только `filter_live_subscribe_ids(None, …)` недостаточно.

### F04. Камеры одного run отменяют запросы друг друга

**Места:** `frontend/src/features/live/useLiveGridPreviewWs.ts:172,211–217`.

`notifyAbort` и `notifyGen` расположены в `connectRun`, поэтому общие на все `source_id`. Пока JPEG камеры 0 загружается, notify камеры 1 отменяет его. При частых уведомлениях и медленном HTTP это приводит к голоданию кадров и лишним запросам. Probe применяет только frame `7:1`; запрос `7:0` получает abort.

**Исправление:** состояние загрузки по `(authEpoch, runId, sourceId)`, один active fetch и последнее ожидающее уведомление на источник; ограничение общего параллелизма отдельно. Отмена при удалении run/source, reconnect, auth change и unmount. Удалять frames/blob URLs завершённых run, а не только при общем unmount.

**Приёмка:** два и 16 источников с разными задержками; уведомление B не отменяет A, старый ответ A не заменяет новый A; повторный 304 согласован с реально применённым blob; после удаления источник не возвращает кадр и не удерживает blob.

### F05. Фоновая фаза отменяет себя собственным изменением state

**Места:** `features/playback/useDetectionIndex.ts:229–283,303`.

Effect допускает запуск только при `phase==='primary_done'`, начинает запрос и вызывает `setPhase('background')`. `phase` входит в зависимости этого effect. Следующий render выполняет cleanup с `abort()`, а новый effect немедленно выходит по guard. Воспроизведение: primary и один day request; day request aborted, `backgroundLoading=true` остаётся.

**Исправление:** явные переходы primary/background/done/error, lifecycle controller не должен завершаться при собственном переходе в running. Отделить identity запроса от отображаемого состояния и учитывать generation. Разобрать retry primary: его `finally` не должен объявлять primary завершённым до успешного retry.

**Приёмка:** реальные hooks в React, primary resolve → background resolve, busy/retry, смена даты/камер/viewport и unmount; загрузка завершается, результат применяется ровно к своей generation, spinner снимается.

### F06. Auth scope не завершён как граница lifecycle

**Места:** `auth/authScope.ts`, `features/live/useLiveGridPreviewWs.ts:300`, `features/live/useRunMetadataWs.ts:77,94,371`, `features/journals/useJournalFeed.ts:42,198`, `features/playback/usePlaybackMetadata.ts:62,129`.

Подтверждены три независимых сценария:

1. `bumpAuthScope()` очищает preview frames, но не отменяет notify fetch и не меняет его generation. Поздний ответ восстанавливает frame старого scope.
2. `RunMetadataStore.close()` сохраняет `latestBySource`; store хранится по run и не подписан на auth epoch. Новая подписка после scope bump немедленно получает старый объект (в probe id 12345).
3. `useJournalFeed` guards проверяют новые ответы, но не очищают уже показанные rows и не запускают reload на epoch change при тех же filters. Probe сохраняет старую строку, число запросов остаётся 1.

Дополнительно по коду: `usePlaybackMetadata` очищает общий cache, но не текущий state/in-flight result через epoch guard; `getAuthEpoch` импортирован без использования. Live/MobileLive и filters metadata местами вычисляют `withAuthScope` при записи результата, без захвата scope на старте, поэтому delayed response может попасть уже в новый namespace. Отправка пустой preview subscribe при bump не гарантирует последующую подписку при неизменных props.

**Исправление:** реактивный scope identifier входит в ключи stores, эффекты и generation каждого чувствительного запроса. Брать scope при старте; abort и guard перед cache/state write; очищать displayed state и пересоздавать transport. Покрыть и same-user revoke, и login другим пользователем, и все mobile/desktop paths.

**Приёмка:** удержать ответы старого scope, сменить пользователя/ACL, завершить ответы; ни cache, ни UI не получают старые данные. Уже показанные данные исчезают сразу. Сохранённые права на оставшиеся камеры восстанавливают подписку без ручного refresh страницы.

### F07. Формула round-robin возвращает прежний cursor

**Места:** `features/live/useRunMetadataWs.ts:265–295`.

`ordered` содержит все `sourceKeys`, поэтому `(start + ordered.length) % sourceKeys.length` равно `start`. Бюджет цикла 8 с и два workers обрывают обход, но следующий цикл начинает его с той же камеры. В probe 16 источников и запросы до timeout: за 18 с обходятся 0–7 и снова 0–7, source 15 не посещён, cursor=0.

**Исправление:** cursor от фактически назначенного следующего source; сохранять его при исчерпании бюджета. `stopRestFallback/close` должны отменять pending request и защищать finalizer старого цикла от изменения состояния нового.

**Приёмка:** 16 камер, первые медленные/недоступные, остальные быстрые; каждая получает попытку за ограниченное число циклов, старый цикл не перекрывает новый, fairness подтверждается порядком запросов.

### F08. Исправлен events singleflight, но аналогичная detection-ветка осталась

**Места:** `core/playback_timeline_index.py:505–545`, `_rebuild_detection_ticks`.

Ключ общей работы содержит date/run, но не камеры. Builder возвращает проекцию камер лидера; ожидающий не выполняет свою проекцию/проверку coverage после ожидания. Два синхронизированных потока: Cam1 leader, Cam2 follower; оба получают словарь только с Cam1.

На внешних путях, выбирающих Cam2 из словаря, это проявляется пропавшими детекциями. **Данный эксперимент не доказывает HTTP-утечку Cam1 через каждый detection endpoint**; доказаны неверный shared result и потеря ответа для follower.

**Исправление:** общая работа возвращает index/version либо full payload; каждый caller после неё проверяет собственное coverage и проецирует данные. Coverage expansion должен сохранять записи других камер; single writer/key должен учитывать storage identity там, где она влияет на index.

**Приёмка:** Cam1/Cam2 одновременно на cold и partial index, обе камеры в ответах и на диске; смена root/run/source version, сбой leader и повтор. Не ограничиваться добавлением cameras в ключ при общей записи одного файла.

### F09. Пустые камеры снова вызывают полный event rebuild

**Места:** `core/playback_timeline_index.py:399,658–664`.

`covered_cameras` включает камеры найденных событий и только текущий requested set. При следующей пересборке ранее проверенные пустые камеры забываются. `complete=true` не делает свежий полный индекс покрывающим все запрошенные камеры. Последовательность EmptyA→EmptyB→EmptyA→EmptyB при неизменных пустых источниках вызывает **4 полных сборки**.

**Исправление:** определить семантику complete для всей области источника/версии; либо общий полный индекс отвечает пустым списком без rebuild, либо сохраняется подтверждённое negative coverage той же версии. Нельзя сохранять coverage после смены версии без перепроверки.

**Приёмка:** несколько пустых камер, System, чередование пользователей; неизменный полный индекс не пересобирается. Отдельный real-data test на >10000 событий и позднее окно подтверждает снятие cap.

### F10. Deadline helper не подключён к playback admission; stale повторно освежается

**Места:** `routes/playback.py:46–57,114–197,445–480`, `core/playback_timeline_index.py:180–192`, `core/route_timeouts.py:24`.

State routes действительно передают `slot_sem` в исправленный helper. Playback helper тоже получил этот параметр, но production callers его не передают. Timeline ожидает `_timeline_slots` отдельно: сначала 0.05 с, затем до 15 с, после чего начинается новый route timeout, по умолчанию ещё 15 с. Таким образом, общий deadline от входа не обеспечен. Новый `test_reaudit_playback_queue_deadline.py` проверяет helper с параметром, которого нет на фактическом пути timeline.

Пулы light/metadata ограничивают workers, но admission/число queued tasks перед submit не ограничено; coalescing внутри worker не предотвращает создание очереди. `_schedule_refresh` создаёт daemon thread до захвата permit; хотя job может быстро завершиться без permit, сами попытки создания threads не объединены до spawn. Высота очередей и стоимость этого поведения на нагрузке здесь не измерялись.

**Дополнительный остаток T10:** helper возвращает только value, без признака происхождения. Timeline повторно делает `_remember(..., ttl=happy_ttl)` и для memory-stale, который не обязан иметь поле `stale`; такой ответ получает status `miss`, затем становится fresh. У cameras `items is not None` тоже не отличает fallback от fresh. Повторные timeout могут продлевать stale retention; конечный возраст данных не сохранён.

**Исправление:** deadline создаётся на входе и передаётся через admission→queue→worker; bounded pending/running, coalescing до submit, общие counters. Результат возвращает freshness/source/generated_at, а stale не записывается как freshly computed и не получает новый абсолютный срок жизни.

**Приёмка:** HTTP saturation tests с занятыми slots/executors; полный wall time ограничен одним бюджетом, очереди не растут, отмена не освобождает работающий slot раньше времени. Fake clock: повторные timeouts не обновляют original freshness/stale age; заголовки и UI честно показывают fallback.

### F11. Playback cache budget не является бюджетом процесса

**Места:** `core/playback_cache.py:44–122`, `core/playback_metadata_service.py:25–27,235–244,434–471`, `core/journal_service.py:97–99,293`, `frontend/src/api/dataCache.ts:8`.

Размер entry больше не пересчитывается при каждом eviction — это выполнено. Но JSON objects, day/per-camera metadata indexes, journal stores и browser Map не получают общего ограничения количества/байтов и idle eviction. TTL lookup не равен удалению всех неиспользуемых ключей. Перебор дат/окон/камер оставляет данные в этих слоях.

`remember/recall` делают deepcopy, а `remember` ещё и JSON size estimate. Вынос из lock уменьшает contention, но вызов из async route остаётся синхронной работой event loop. Запрет oversized entry выполняется после копирования и оценки, поэтому не ограничивает временный пик памяти на построение/copy. `bytes_est` — размер сериализуемого представления, не RSS всех Python objects.

**Исправление:** инвентаризация всех stores с owner/lifetime; отдельные bounded policies и суммарные метрики; immutable shared indexes и проекции без глубокого копирования всего дня на loop. Ограничивать данные до создания oversized response, а не только при попытке положить его в cache.

**Приёмка:** soak по нескольким датам/камерам/окнам и auth scopes; RSS/heap стабилизируется после eviction, p95 loop lag и UI long tasks измерены. Без этого нельзя численно утверждать, что память или лаги исправлены.

### F12. Gate расширен, но остаётся красным и пропускает часть новых тестов

**Места:** `scripts/verify_web_journals.sh`, `.github/workflows/web-journals.yml`, новые `test_reaudit_*`, штатные frontend tests.

Из 14 текущих failures:

- **4 непосредственно относятся к новой journal media регрессии:** три preview tests и integration smoke получают 403 вместо 200.
- **6 повторяют категории прежнего аудита:** AF_UNIX на Windows, слишком много чтений mvhd, `include_logs` в mock, basic setup defaults, два auth fixtures. Конкретный mvhd count сейчас 19, раньше 11; одного падения недостаточно для вывода о новой performance-регрессии.
- **1 прежний retargeted stale test** теперь доходит до поведения и падает на пустом списке вместо прежнего AttributeError; замена ссылки на cache сама по себе его не исправила. Fixture и фактическую индексную ветку нужно согласовать.
- **1 cancellation test** `test_media_inflight_released_when_resolve_cancelled` дал TimeoutError. Это наблюдение текущего прогона; отдельный вывод о production leak без анализа scheduling делать нельзя.
- **2 resolver tests** сравнивают Windows пути с разными разделителями. Это дополнительный к прежнему API-набору scope, а не доказанные новые Linux-регрессии.

Шесть из семи прежних cache-interface failures больше не падают; седьмой имеет описанный выше behavioral failure. Полные идентификаторы сохранены в validation JSON, без stdout с автоматически создаваемыми тестовыми паролями.

CI script включает больше ACL/cache/state тестов, но **не включает** новые `test_reaudit_playback_queue_deadline.py`, `test_reaudit_live_ws_kick.py` и meta exit-status test. Trigger на `test_reaudit_*` не означает исполнение каждого такого файла. Linux CI execution здесь не проверен, но preview failure воспроизводится независимо от Windows separator.

Штатные 180 frontend tests проходят, при этом 6 дополнительных сценариев реальных hooks/stores подтверждают ошибки. Тестирование чистого predicate или вручную сконструированного cache key не проверяет cleanup, subscriptions, эффекты и delayed responses.

**Исправление:** обязательный согласованный API-набор; OS-specific tests явно отделены; актуальные фикстуры и наблюдаемый pytest exit. Добавить настоящие route/hook tests для F01–F10 и включить их в исполняемый gate. Не менять expected 200 на 403 для легитимных media ради зелёного CI.

### F13. Измерения пока не подтверждают устранение web-ui lag

**Места:** `scripts/audit_perf_probe.py:107–127,288–327`, `reports/audit_perf_probe_reaudit.json`, `reports/audit_perf_measured_2026-09-23.md`.

Исправлены получение media path из timeline, `ticks_only=true`, fallback на `/ready`. Новый сохранённый прогон действительно содержит успешные timeline/detections/events/media и readiness diagnostics.

Однако остаются ограничения:

- `--reps 5`, 5 live камер и один архивный camera/day не покрывают условия 16 камер, cold/warm, WAN/reconnect и soak.
- JSONL назван raw samples, но хранит целый агрегированный report: per-request timings/codes с timestamp и фазой warm не сохраняются. p95/p99 по 5 samples нестабильны для приёмки хвостов.
- Gate проверяет лишь наличие хотя бы одного 200/304 среди required endpoints, включая warm; смешанный прогон с ошибками может считаться успешным. State/snapshot/media не входят в этот required set.
- Media измеряет получение **180135727 байт полного файла**, p95 около 2059 мс. Это не Range seek latency и не время до первого показанного кадра.
- Сохранённые detections: **3198770 байт**, p95 **622.46 мс** даже с `ticks_only`; timeline p95 **377.43 мс**. Это основания исследовать payload/serialization, но не измерение React lag.
- Нет browser long tasks, frame age, first useful frame/marker, reconnect trace, React Profiler, CPU/RSS/loop-lag time series. Исторический текст отчёта местами дополнен утверждениями о новой реализации; сравнения разных payload/дней нужно разделить по SHA и условиям.

**Исправление:** raw samples с полным manifest (SHA/config/host/data size/network), явные error budget и acceptance thresholds; парные прогоны одинакового сценария. Отдельно API, decode/paint и React commit cost. T17 разрешать по профилю, без заранее заданного ненужного render refactor.

## 5. Сверка всех задач предыдущего плана

Статус «частично» означает наличие полезной реализации при незакрытых условиях приёмки. «Не подтверждено» не означает автоматически отсутствие улучшения.

| Задача | Статус на dcfc98dd | Остаток |
|---|---|---|
| T01 — починить tests | Частично | 14 failures текущего расширенного набора; F12 |
| T02 — probes в regression tests | Частично | Есть ACL/events/ticks/cache/deadline tests; отсутствуют positive media, настоящие hooks, session revoke и detection followers |
| T03 — CI/exit gate | Частично | Расширены script/triggers; новые файлы и meta test исполняются не все, F12 |
| T04 — canonical media | Частично, с регрессией | Canonical ACL работает; ownership текущих images/дефисов не решён, F02 |
| T05 — общий build / projection | Частично | Events исправлен; detections F08 |
| T06 — отзыв transport | Частично, с регрессией | Pending/kick реализованы; F01/F03, metadata WS/MJPEG |
| T07 — frontend auth scope | Частично | Epoch/keys добавлены; lifecycle/state/stores F06 |
| T08 — versioned ticks | Основной дефект R04 исправлен | Нужна приёмка append/change/delete/restart и concurrent coverage F08; не считать весь индексный контракт закрытым |
| T09 — full event index | Частично | Cap снят; negative coverage F09, большой день не доказан текущими tests |
| T10 — fresh/stale | Частично | Cache-level fresh miss исправлен; происхождение и конечный возраст route fallback F10 |
| T11 — admission/deadline/accounting | Частично | State подключён; playback callers/queues F10 |
| T12 — бюджеты caches | Частично | Playback entry nbytes/oversized есть; остальные layers и loop copies F11 |
| T13 — Live lifecycle/notify/visibility | Частично, с регрессией | Per-run cleanup и empty visibility улучшены; F04/F06 |
| T14 — fair metadata fallback | Не закрыта | Ограниченный параллелизм есть, cursor не продвигается, F07 |
| T15 — detection state machine | Не закрыта, регрессия | Self-abort background, F05 |
| T16 — journal state machine | Частично | Catch/deadline улучшены; scope reset F06; poll без собственного deadline/single-flight требует проверки при медленной сети |
| T17 — render isolation по профилю | Не подтверждено | Нет Profiler acceptance; не выводить необходимость рефакторинга из размера файла |
| T18 — измерения | Частично | Исправлен probe и есть новый JSON; методика и UI измерения F13 |
| T19 — рефакторинг по контрактам | Частично | Есть ArchiveMediaResolver facade, CachePolicy, event projection helpers; detection/ownership/scheduler/frontend store contracts ещё расходятся с docs |

По R01–R17: исходные конкретные механизмы **R04 и R11 исправлены** в проверенном объёме; R01/R02/R03/R05/R06/R07/R08/R09/R10/R12/R13/R14/R15/R16/R17 требуют указанных условий/доработок. Особенно нельзя закрывать R03 по одному events test или R09 по наличию `auth:` в ключе.

## 6. План следующего исправления

Оценки — относительный объём: S до одного небольшого изменения, M несколько связанных модулей, L сквозной контракт с тестами. Это не календарное обещание.

| Порядок | Работа | Объём | Проверяемый результат |
|---|---|---|---|
| 1 / P0 | Актуальный principal и отзыв сессий/transport, F01 | L | Сохранённые cookies и открытые transports теряют отозванные права; положительные роли работают |
| 2 / P1 | Media owner model по реальным writer layouts, F02 | L | Journal previews/frames/video 200/206 для разрешённых, 403 для чужих; traversal остаётся закрыт |
| 3 / P1 | Развести unrestricted/deny и проверить весь WS route, F03 | S–M | Admin/auth-disabled подписываются и получают pong; empty ACL отклоняется |
| 4 / P1 | Per-source notify lifecycle, F04, вместе с scope guard F06 | M | Все камеры обновляются; поздние/отозванные ответы не применяются, blobs освобождаются |
| 5 / P1 | Исправить detection phases, F05 | M | Primary и day enrichment завершаются; retry/смена props/unmount не дают вечного spinner |
| 6 / P1 | Включить auth epoch во все stores/effects/state, F06 | L | Same-user ACL revoke очищает UI и старые запросы; разрешённые подписки восстанавливаются |
| 7 / P1 | Detection full build/projection, F08; event coverage F09 | M–L | Конкурентные callers и пустые камеры корректны без повторных full rebuild |
| 8 / P1 | Deadline/admission и metadata результата, F10 | L | Один бюджет HTTP; bounded queues; stale не омолаживается |
| 9 / P1 | Починить/включить обязательные tests, F12 | M, параллельно 1–8 | API и frontend gate зелёные по ожидаемому поведению, все новые regression tests исполняются |
| 10 / P2 | Фактическое продвижение metadata cursor, F07 | S–M | 16 камер обслуживаются справедливо даже при timeout первых |
| 11 / P2 | Journal poll/reload lifecycle и ошибки deadline | M | Нет overlap при медленном poll, понятное завершение timeout, отмена на scope/filter/unmount |
| 12 / P1–P2 | Budgets всех caches и устранение тяжёлых loop copies, F11 | L | Память и loop latency в заданных пределах на soak; метрики всех слоёв |
| 13 / P2 | Воспроизводимый perf harness и browser profiles, F13 | M–L | Raw samples + сравнимый manifest, 1/4/16 камер, cold/warm, Range seek, WAN, 30–60 мин soak |
| 14 / P3 | Закрепить границы модулей после 1–13 | M–L | Resolver owns path/type/owners; index repository owns version/build/projection; scheduler owns deadlines/queues; stores own scope/lifetime |

Минимальные merge gates каждого функционального исправления: red-before/green-after reproducer, штатные API/frontend/typecheck/build, проверка positive и negative сценария, совпадение собранной SPA с source. Для memory/perf задач отдельно записать численные бюджеты на согласованном стенде, а не принимать факт наличия метрики как достижение цели.

## 7. Почему это было упущено

1. **Проверялась локальная функция, но не вызывающий маршрут.** Примеры: playback `slot_sem` и unrestricted WS.
2. **Отрицательные ACL-примеры преобладали над положительными.** Запрет чужого файла проверен, текущий writer layout разрешённого изображения — нет.
3. **Исправление применялось к одному из сходных путей.** Events/detections; preview WS/metadata WS/MJPEG; cache/state/in-flight.
4. **Идентичность пользователя, source и запроса смешивалась.** Run-level abort для разных камер; session role вместо актуальной; cache clear вместо полного scope lifecycle.
5. **Наличие состояния принималось за его правильный переход.** `phase`, `restCursor`, `complete` введены, но переходы не проверены на реальном consumer.
6. **Названия коммитов и docs шире доказательств.** T18 «samples» агрегированы, T19 facade ещё не владеет всеми контрактами, T01–T03 ещё не дают зелёный gate.

Для следующего цикла нужен checklist по пользовательским сценариям и границам данных, а не только отметка R/T в сообщении коммита.

## 8. Артефакты и воспроизведение

- [backend_probes.py](audit_dcfc98dd/backend_probes.py), [backend_results.json](audit_dcfc98dd/backend_results.json).
- [frontend_probes.test.ts](audit_dcfc98dd/frontend_probes.test.ts), [vitest.config.mjs](audit_dcfc98dd/vitest.config.mjs), [frontend_results.json](audit_dcfc98dd/frontend_results.json).
- [validation_summary.json](audit_dcfc98dd/validation_summary.json), [revision_range.json](audit_dcfc98dd/revision_range.json).

Из корня checkout проверяемого SHA, с установленными API/test dependencies:

```text
python reports/audit_dcfc98dd/backend_probes.py --out backend-results.json
python -m pytest tests/unit/api tests/unit/meta/test_pytest_exit_status.py tests/unit/visualization/test_journal_media_resolver.py tests/integration/api/test_journals_smoke.py -q --tb=short
npm ci --prefix evileye/api/frontend
npm test --prefix evileye/api/frontend
npm install --prefix evileye/api/frontend --no-save --package-lock=false react-test-renderer@18.3.1
node evileye/api/frontend/node_modules/vitest/vitest.mjs run --config reports/audit_dcfc98dd/vitest.config.mjs
npm ci --prefix evileye/api/frontend
```

Последний `npm ci` удаляет временный renderer и возвращает locked dependencies. Аудиторские frontend probes пишут собственный JSON в папку отчёта. Для штатной сборки использовать отдельный outDir либо заранее учитывать изменения tracked static assets. Изолированные Python зависимости текущей проверки перечислены в validation JSON.
