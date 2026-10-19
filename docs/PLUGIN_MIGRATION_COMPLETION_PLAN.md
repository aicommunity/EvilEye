# Миграция расширяемых модулей: текущий статус

Краткий актуальный статус. Полный хронологический журнал прогонов (2026-10-10 … 2026-10-13)
перенесён в [`docs/history/PLUGIN_MIGRATION_COMPLETION_PLAN_LOG.md`](history/PLUGIN_MIGRATION_COMPLETION_PLAN_LOG.md);
он описывает историю, а не текущий чек-лист.

## Что сделано

- Единый plugin SPI для источников, детекторов, трекеров, событий и пайплайнов; контракты — в
  [`PLUGINS.md`](PLUGINS.md), архитектура — в [`PIPELINE_ARCHITECTURE.md`](PIPELINE_ARCHITECTURE.md).
- Встроенные модули зарегистрированы через тот же SPI; parity-тесты сверяют их со старой реализацией.
- Внешний пакет (`examples/plugin_package`) проходит lifecycle, `extend`/`replace` в
  `PipelineSurveillance`, режимы `thread` и `process`.
- Микрозамеры накладных расходов runtime — [`PLUGIN_RUNTIME_BENCHMARK.md`](PLUGIN_RUNTIME_BENCHMARK.md)
  (1080p, process round-trip: p50 6.3–6.8 мс, p95 7.1–7.9 мс; thread: p95 < 0.7 мс).

## Аудит ветки `plugin_support` от 2026-10-19

| Этап | Содержание | Статус |
| --- | --- | --- |
| 0 | CI: `.github/workflows/ci.yml` (ruff-гейт новых F821/E9, unit на py3.10/3.12, фронтенд, smoke внешнего пакета, проверка оставшихся worker-ов) | Сделано |
| 1 | P0: недостающие импорты (A3, C3), `error_policy` и перезапуск воркеров (A1, A2) | Сделано |
| 2 | Безопасность: изоляция сбойных плагинов (B1), прокси и `builder_allowed_ips` (B2), CSRF по Origin, пароль при установке, имена плагинов (B3), threadpool и кеш (B4), блокировки и ротация операций (C4) | Сделано |
| 3 | Корректность: ремап `class_id` (B5), `degraded` в скользящем окне и Prometheus (B6), лимиты и пустой ответ fanout (C1, C2), документация границы процесса (C5) | Сделано, см. ограничения |
| 4 | Техдолг: разбиение модулей, гигиена репозитория | В работе, см. [`TECH_DEBT.md`](../TECH_DEBT.md) |

Ограничения этапа 3: общий shared-memory сегмент между стадиями не вводился (кадр мог быть изменён
предыдущей стадией); детектор без опубликованного `model_class_mapping` в multi-detector fanout не
ремапится и не вызывает ошибку старта.

## Критерии первой версии

Результаты проверок 2026-10-19: [`RUNTIME_VERIFICATION_2026-10-19.md`](RUNTIME_VERIFICATION_2026-10-19.md).

1. Целевые FPS, p95 и допустимая доля потерь: **не заданы**. Сравнение с `main` выполнено: ветка теряет на ~10 п.п.
   кадров больше (TD-PS-D7), нужен профиль по стадиям.
2. Тревога в настоящем браузере и camera ACL: **выполнено** (`scripts/alarm_browser_check.py`), по ходу исправлены
   три дефекта.
3. Обрыв и восстановление RTSP: **выполнено** на потоке `cvlc` для GStreamer и OpenCV
   (`scripts/rtsp_disconnect_check.py`).
4. Прогнать CI из этапа 0 на GitHub и закрепить его как release gate: **не выполнено** (нужен пуш).

Вне первой версии: durable alarm outbox после аварийного завершения, универсальный DAG, hot-plug,
автоустановка зависимостей, sandbox стороннего Python-кода и process-режим для синхронного
`ObjectMultiCameraTracking`. Python-плагин исполняется с правами процесса EvilEye; process mode не
является границей безопасности.
