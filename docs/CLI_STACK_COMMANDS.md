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
| `start CONFIG [--gui] [--detach] [--release]` | managed (если web active) или direct run |
| `restart CONFIG` | stop + start с grace |

`--hold` пишет `monitor/.manual_stop_until` (watchdog не перезапустит pipeline ~1ч).

## `evileye reload`

| Подкоманда | Описание |
|------------|----------|
| `web [--force-build] [--with-pipeline] [--config CONFIG]` | Правильный порядок: stop pipeline → build → service restart → start pipeline |
| `backend` | Только restart OS web service |
| `pipeline CONFIG` | Только pipeline |

**Типичный dev-цикл после правки SPA/API:**

```bash
evileye reload web --with-pipeline --config configs/system.json
```

## `evileye prod`

| Подкоманда | Описание |
|------------|----------|
| `init CONFIG` | `deploy` + `service install` + watchdog + site profile |
| `up` | `service start` + pipeline (auto managed/direct) |
| `down [--stop-service]` | `pipeline stop --hold` |
| `restart [--with-pipeline]` | Полный ordered reload |

Профиль сайта: `.evileye_service.json` (`production_config`, `pipeline_launch: auto`).

## `evileye dev server`

Foreground `evileye server --no-reload` без systemd.

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
