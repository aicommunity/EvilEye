# Команды `evileye install-server` / `evileye uninstall-server`

## Обзор

Команды устанавливают и удаляют **OS-сервис приложения** EvilEye (Web UI / FastAPI), отдельно от watchdog-таймеров в `monitor/`. HTTPS настраивается здесь же (интерактивно или флагами).

| Команда | Назначение |
|---------|------------|
| `evileye deploy` | Только файлы сайта для локальной работы (без вопросов, без сервиса) |
| `evileye install-server [CONFIG]` | Если окружение Web UI не готово — `setup-web`, затем TLS-мастер + OS-сервис |
| `evileye uninstall-server` | Остановить и удалить сервис |
| `evileye setup-web` | Явная проверка/починка Python API + SPA (необязательно, если вызываете `install-server`) |

Это **не** то же самое, что `monitor/scripts/install_timer.sh` (watchdog health-check).

Штатный порядок:

```bash
cd /opt/evileye-site
evileye deploy              # локальные файлы сайта
evileye install-server      # только если нужен сервер Web UI
```

## install-server

Сначала проверяет окружение Web UI (`fastapi`/`uvicorn`/SPA static). Если чего-то не хватает —
печатает, что не готово, вызывает тот же путь, что `evileye setup-web`, и **продолжает только после
успешной повторной проверки**. Отсутствие системной `libturbojpeg` не блокирует установку
(preview через OpenCV). Если починить окружение нельзя (нет npm для сборки SPA и т.п.) — выход с кодом 1, сервис не ставится.

Без конфига (минимальный post-install режим):

```bash
evileye install-server
# эквивалент сервиса после TLS-шага:
# evileye server --host 0.0.0.0 --port 8181 --no-reload [--ssl-certfile … --ssl-keyfile …]
```

Создаёт `configs/system.json` (каркас без камер/БД), если файла нет.

С конфигом (auto-run после старта API):

```bash
evileye install-server configs/my.json
# или:
evileye install-server my.json
```

### HTTPS

Интерактивно (TTY): Enable HTTPS? → self-signed или existing PEM → SAN IP и/или DNS.

CI / без TTY:

```bash
evileye install-server --non-interactive --no-tls
evileye install-server --non-interactive --tls-self-signed --tls-ip 127.0.0.1
evileye install-server --non-interactive --tls-self-signed --tls-ip 192.168.1.50 --tls-dns evileye.lan
```

Другие флаги: `--ssl-certfile` / `--ssl-keyfile`, `--tls-force`. Без TTY и без TLS-флагов сервис ставится как HTTP + warning запустить команду в терминале.

После самоподписи импортируйте `certs/ca.crt` на клиентах. Приватные ключи `certs/*.key` не коммитить.

Опции сервиса:

- `--host` / `--port` (по умолчанию `0.0.0.0` / `8181`)
- `--user` — systemd user unit (Linux, по умолчанию для CLI)
- `--system` — system unit (может потребовать sudo)
- `--dry-run` — показать unit без применения (`ExecStart` содержит `--ssl-*`, если TLS настроен)

Состояние сайта: `.evileye_service.json` (не коммитить).

### Linux

- User: `~/.config/systemd/user/evileye.service`
- System: `/etc/systemd/system/evileye.service`
- Шаблон: [`deploy/service/evileye.service.in`](../deploy/service/evileye.service.in)

### Windows (best-effort → supported)

Генерируется `scripts/evileye-server.bat`; регистрируется Scheduled Task **`EvilEye`** (`ONSTART`, `/RL HIGHEST`). NSSM не требуется. Нужны права администратора для `schtasks`.

Ручной запуск при ошибке Task: двойной клик по `.bat` или:

```powershell
schtasks /Run /TN EvilEye
```

Полный native bring-up: [WINDOWS_NATIVE.md](WINDOWS_NATIVE.md).

Watchdog (отдельно от service):

```powershell
evileye watchdog-install --config configs/single_video.json
```

## uninstall-server

```bash
evileye uninstall-server
```

Повторный вызов безопасен («не установлен»).

## После установки

1. Откройте `http://127.0.0.1:8181` (или `https://…`, если включён TLS) / хост машины.
2. Войдите как `admin` (пароль bootstrap — в логе сервиса при первом старте).
3. Смените пароль и завершите базовую настройку в Web UI.

## Troubleshooting

```bash
systemctl --user status evileye
journalctl --user -u evileye -n 100
evileye uninstall-server
evileye install-server --dry-run --no-tls
```
