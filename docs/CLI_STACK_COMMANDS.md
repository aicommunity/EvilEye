# Управление стеком EvilEye (CLI)

Единый интерфейс для Web UI, OS-сервиса и pipeline runtime.

**Site directory** = текущий cwd (обычно каталог deploy-сайта, например `~/EvilEyeDeploy`). Запускайте команды из корня сайта.

## Миграция со старых команд

| Было | Стало |
|------|-------|
| `evileye setup-web` | `evileye web check` / `evileye web build` / `evileye web deps` |
| `evileye setup-web --force` | `evileye web build --force` или `evileye reload web --force-build` |
| `evileye install-server` | `evileye service install` |
| `evileye uninstall-server` | `evileye service uninstall` |
| `systemctl --user restart evileye` | `evileye service restart` |
| ручной stop + restart pipeline | `evileye pipeline restart` (CONFIG optional) |
| неясно что запущено | `evileye status` |

## Три сценария

| Сценарий | Команды |
|----------|---------|
| **Разработка pipeline** | `evileye run CONFIG [--gui]` |
| **Разработка Web UI / API** | `evileye dev server`, `evileye reload web` |
| **Production на хосте** | `evileye prod init CONFIG` → `evileye prod up` |

## Что нажать когда (decision table)

| Ситуация | Команда |
|----------|---------|
| Всё ок / посмотреть состояние | `evileye status` |
| После правки SPA/API, pipeline не трогать | `evileye reload web` |
| Перезапустить только pipeline | `evileye pipeline restart` или `evileye reload pipeline` |
| Полный reload web + pipeline | `evileye prod restart` или `evileye reload web --with-pipeline` |
| Web service не активен | `evileye service start` |
| Дубли pipeline | `evileye pipeline stop --all` затем `evileye pipeline start` |
| Web collision (service + stray foreground) | `evileye service restart` |
| Остановить prod (hold watchdog) | `evileye prod down` |
| Поднять prod заново | `evileye prod up` |

**`prod restart`** по умолчанию **с pipeline** (`--with-pipeline`).  
**`reload web`** по умолчанию **только web** (pipeline не трогает).

## Резолв CONFIG (порядок)

Для `pipeline restart`, `reload pipeline`, `prod up/restart`, `reload web --with-pipeline`:

1. Явный аргумент / `--config`
2. Ровно один живой pipeline на site → его `config_path`
3. `production_config` из `.evileye_service.json`
4. `watchdog_config` из профиля
5. Иначе — ошибка с подсказкой (`prod init` / `service install`)

Если запущено **несколько** разных configs — нужно указать CONFIG явно.

Для `pipeline start` без аргумента: только профиль (п.3–4), **не** берётся уже running config.

## `evileye status [--json]`

Показывает:

1. Таблицу стека (OS service, порт, PIDs, pipeline counts, watchdog)
2. Active pipeline runs
3. Warnings
4. **Recommended** — контекстные команды (1–3), с приоритетом проблем (дубли, collision, service down)
5. **Commands** — компактный справочник основных операций

`--json` включает `suggested_commands` и `command_catalog`.

## `evileye web`

| Подкоманда | Описание |
|------------|----------|
| `check` | Проверка Python deps + SPA static |
| `deps [--scope user\|system]` | Установка Python-пакетов API |
| `build [--force]` | `npm install && npm run build` |
| `refresh [--force]` | build при необходимости + `evileye service restart` |

## `evileye service`

| Подкоманда | Описание |
|------------|----------|
| `install [CONFIG]` | TLS (опционально) + OS unit (systemd / Windows Task); пишет `production_config` |
| `uninstall` | Удаление сервиса |
| `start` / `stop` / `restart` / `status` | Управление unit |

Флаги TLS: `--no-tls`, `--tls-self-signed`, `--tls-ip`, `--ssl-certfile`, …

## `evileye pipeline`

| Подкоманда | Описание |
|------------|----------|
| `status` | Активные runs |
| `stop --config CONFIG` / `stop --all` | Остановка; **обязателен** `--config` или `--all` |
| `start [CONFIG] [--gui] [--detach] [--release] [--replace]` | managed (если web active) или direct; CONFIG optional из профиля |
| `restart [CONFIG]` | stop + start; CONFIG optional (unique run или профиль) |

**Singleton policy (per-site):** без `--replace` команды `pipeline start`, `evileye run` и API start завершаются с ошибкой, если для того же config уже есть живой `process.py`. `evileye prod up` идемпотентен. Явный перезапуск: `pipeline restart` или `pipeline start --replace`.

`--hold` пишет `monitor/.manual_stop_until` (watchdog не перезапустит pipeline ~1ч).

Примеры:

```bash
evileye pipeline restart                          # один живой run
evileye pipeline restart configs/poly-cameras-gst.json
evileye pipeline stop --all --hold
evileye pipeline start --release                  # из production_config
```

## `evileye reload`

| Подкоманда | Описание |
|------------|----------|
| `web [--force-build] [--with-pipeline] [--config CONFIG]` | Build → service restart → (опционально) pipeline |
| `backend` | Только restart OS web service |
| `pipeline [CONFIG]` | Только pipeline (как `pipeline restart`) |

**`reload web` без `--with-pipeline` не трогает pipeline.**

```bash
evileye reload web
evileye reload web --with-pipeline
evileye reload pipeline
```

## `evileye run`

| Флаг | Описание |
|------|----------|
| `--replace` | Остановить существующий run для этого config, затем запустить |

Без `--replace` — fail fast с pid и подсказкой `pipeline restart`.

## `evileye prod`

| Подкоманда | Описание |
|------------|----------|
| `init CONFIG` | `deploy` + `service install` + watchdog + site profile |
| `up` | `service start` + pipeline (profile / unique running); idempotent |
| `down [--stop-service]` | stop all pipelines + hold |
| `restart [--with-pipeline/--web-only] [--config]` | Ordered reload; default **with pipeline** |

Профиль сайта: `.evileye_service.json` (`production_config`, `pipeline_launch: auto`, `gui_default: false`).

## `evileye dev server`

Foreground `evileye server --no-reload` без systemd. Не запускается, если OS service активен, порт занят или уже есть foreground `evileye server` для этого site.

## Диагностика дублей

`evileye status` показывает предупреждения:

- `duplicate_pipeline_detected` — несколько живых `process.py` на один config → Recommended: `pipeline stop --all`
- `web_collision` — OS service + лишний foreground server → Recommended: `service restart`

### Залипшие bbox на Live / рост RAM pipeline

1. Снимок baseline: `scripts/diagnose_live_bbox_baseline.sh` (RSS, `/ready`, top процессов).
2. Метрики handler: `curl -s http://127.0.0.1:8181/ready | jq .objects_handler`
3. Диагностика в логе: `EVILEYE_PERF_DIAG=1 EVILEYE_PERF_DIAG_EVERY=30`
4. Сброс памяти: `evileye reload pipeline` (CONFIG optional при одном run)

## Docker

В контейнере `evileye service *` недоступен. Используйте:

| Native | Docker Compose |
|--------|----------------|
| `evileye reload web` | `docker compose restart web` |
| `evileye pipeline stop --all` | `docker compose stop app` |
| `evileye prod up` | `docker compose up -d` |

Compose по-прежнему запускает `evileye server` и `evileye run` в отдельных контейнерах `web` и `app`.

## См. также

- [CLI_DEPLOY_COMMAND.md](CLI_DEPLOY_COMMAND.md)
- [WEB_UI_GUIDE.md](WEB_UI_GUIDE.md)
- [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md)
