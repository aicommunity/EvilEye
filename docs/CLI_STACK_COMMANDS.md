# Управление стеком EvilEye (CLI)

Единый интерфейс для Web UI, OS-сервиса и pipeline runtime.

## Миграция со старых команд

| Было | Стало |
|------|-------|
| `evileye setup-web` | `evileye web check` / `evileye web build` / `evileye web deps` |
| `evileye setup-web --force` | `evileye web build --force` или `evileye reload web --force-build` |
| `evileye install-server` | `evileye service install` |
| `evileye uninstall-server` | `evileye service uninstall` |
| `systemctl --user restart evileye` | `evileye service restart` |
| ручной stop + restart pipeline | `evileye pipeline restart CONFIG` |
| неясно что запущено | `evileye status` |

## Три сценария

| Сценарий | Команды |
|----------|---------|
| **Разработка pipeline** | `evileye run CONFIG [--gui]` |
| **Разработка Web UI / API** | `evileye dev server`, `evileye reload web` |
| **Production на хосте** | `evileye prod init CONFIG` → `evileye prod up` |

## `evileye status [--json]`

Показывает OS-сервис, порт :8181, foreground server, pipeline runs, watchdog hold/grace и рекомендуемую команду.

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
| `install [CONFIG]` | TLS (опционально) + OS unit (systemd / Windows Task) |
| `uninstall` | Удаление сервиса |
| `start` / `stop` / `restart` / `status` | Управление unit |

Флаги TLS те же, что у прежнего `install-server`: `--no-tls`, `--tls-self-signed`, `--tls-ip`, `--ssl-certfile`, …

## `evileye pipeline`

| Подкоманда | Описание |
|------------|----------|
| `status` | Активные runs |
| `stop [--all] [--hold]` | Остановка + опционально блокировка watchdog |
| `start CONFIG [--gui] [--detach] [--release] [--replace]` | managed (если web active) или direct run |
| `restart CONFIG` | stop + start с grace |

**Singleton policy (per-site):** без `--replace` команды `pipeline start`, `evileye run` и API start завершаются с ошибкой, если для того же config уже есть живой `process.py` на этом site. `evileye prod up` идемпотентен (пропускает уже запущенный pipeline). Явный перезапуск: `--replace` или `pipeline restart`.

`--hold` пишет `monitor/.manual_stop_until` (watchdog не перезапустит pipeline ~1ч).

## `evileye reload`

| Подкоманда | Описание |
|------------|----------|
| `web [--force-build] [--with-pipeline] [--config CONFIG]` | Build → service restart → (опционально) pipeline restart |
| `backend` | Только restart OS web service |
| `pipeline CONFIG` | Только pipeline |

**`reload web` без `--with-pipeline` не трогает pipeline** — только web-слой (build + `service restart`). Используйте это после правок SPA/API, когда pipeline должен продолжать работать.

**`reload web --with-pipeline`** останавливает pipeline, перезапускает web и стартует pipeline с `--replace` (на случай managed-only child, не попавшего в stop).

**Типичный dev-цикл после правки SPA/API (pipeline трогать не нужно):**

```bash
evileye reload web
```

**Полный reload web + pipeline:**

```bash
evileye reload web --with-pipeline --config configs/system.json
```

## `evileye run`

| Флаг | Описание |
|------|----------|
| `--replace` | Остановить существующий run для этого config на site, затем запустить |

Без `--replace` — fail fast с pid и подсказкой, если pipeline уже запущен.

## `evileye prod`

| Подкоманда | Описание |
|------------|----------|
| `init CONFIG` | `deploy` + `service install` + watchdog + site profile |
| `up` | `service start` + pipeline (auto managed/direct) |
| `down [--stop-service]` | `pipeline stop --hold` |
| `restart [--with-pipeline]` | Полный ordered reload |

Профиль сайта: `.evileye_service.json` (`production_config`, `pipeline_launch: auto`).

## `evileye dev server`

Foreground `evileye server --no-reload` без systemd. Не запускается, если OS service активен, порт занят или уже есть foreground `evileye server` для этого site.

## Диагностика дублей

`evileye status` показывает предупреждения:

- `duplicate_pipeline_detected` — несколько живых `process.py` на один config
- `web_collision` — OS service активен и одновременно есть foreground server

Рекомендуемые команды: `evileye pipeline stop --all`, `evileye service restart`.

### Залипшие bbox на Live / рост RAM pipeline

1. Снимок baseline: `scripts/diagnose_live_bbox_baseline.sh` (RSS, `/ready`, top процессов).
2. Метрики handler: `curl -s http://127.0.0.1:8181/ready | jq .objects_handler` — `active_objects`, `active_last_image_bytes`, `stale_source_ids`.
3. Подробные счётчики в логе pipeline: `EVILEYE_PERF_DIAG=1 EVILEYE_PERF_DIAG_EVERY=30` (systemd unit или env перед `evileye reload pipeline`).
4. После hotfix: `evileye reload pipeline <config>` — сбрасывает накопленную память; проверить Live bbox на пустой сцене.

## Docker

В контейнере `evileye service *` недоступен. Используйте:

| Native | Docker Compose |
|--------|----------------|
| `evileye reload web` | `docker compose restart web` |
| `evileye pipeline stop` | `docker compose stop app` |
| `evileye prod up` | `docker compose up -d` |

Compose по-прежнему запускает `evileye server` и `evileye run` в отдельных контейнерах `web` и `app`.

## См. также

- [CLI_DEPLOY_COMMAND.md](CLI_DEPLOY_COMMAND.md)
- [WEB_UI_GUIDE.md](WEB_UI_GUIDE.md)
- [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md)
