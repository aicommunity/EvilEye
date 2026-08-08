# Команды `evileye service-install` / `evileye service-uninstall`

## Обзор

Команды устанавливают и удаляют **OS-сервис приложения** EvilEye (Web UI / FastAPI), отдельно от watchdog-таймеров в `monitor/`.

| Команда | Назначение |
|---------|------------|
| `evileye service-install [CONFIG]` | Установить и запустить сервис (идемпотентно) |
| `evileye service-uninstall` | Остановить и удалить сервис |
| `evileye deploy` | В конце вызывает ensure `service-install` (ошибка сервиса не валит deploy) |

Это **не** то же самое, что `monitor/scripts/install_timer.sh` (watchdog health-check).

## service-install

Без конфига (минимальный post-install режим):

```bash
evileye service-install
# эквивалент сервиса:
# evileye server --host 0.0.0.0 --port 8181 --no-reload
```

Создаёт `configs/system.json` (каркас без камер/БД), если файла нет.

С конфигом (auto-run после старта API):

```bash
evileye service-install configs/my.json
# или:
evileye service-install my.json
```

Опции:

- `--host` / `--port` (по умолчанию `0.0.0.0` / `8181`)
- `--user` — systemd user unit (Linux, по умолчанию для CLI)
- `--system` — system unit (может потребовать sudo)
- `--dry-run` — показать unit без применения

Состояние сайта: `.evileye_service.json` (не коммитить).

### Linux

- User: `~/.config/systemd/user/evileye.service`
- System: `/etc/systemd/system/evileye.service`
- Шаблон: [`deploy/service/evileye.service.in`](../deploy/service/evileye.service.in)

### Windows (best-effort)

Генерируется `scripts/evileye-server.bat`; по возможности регистрируется Scheduled Task. NSSM не требуется.

## service-uninstall

```bash
evileye service-uninstall
```

Повторный вызов безопасен («не установлен»).

## После установки

1. Откройте `http://127.0.0.1:8181` (или хост машины).
2. Войдите как `admin` (пароль bootstrap — в логе сервиса при первом старте).
3. Смените пароль и завершите базовую настройку в Web UI.

## Troubleshooting

```bash
systemctl --user status evileye
journalctl --user -u evileye -n 100
evileye service-uninstall
evileye service-install --dry-run
```
