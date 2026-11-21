# Команда `evileye service`

Управление OS-сервисом Web UI (systemd / Windows Scheduled Task) и HTTPS.

См. полный гайд: [CLI_STACK_COMMANDS.md](CLI_STACK_COMMANDS.md).

## Быстрый старт

```bash
cd /opt/evileye-site
evileye deploy
evileye service install              # TLS wizard + unit
evileye service install configs/my.json   # + autorun config в unit
```

## Подкоманды

| Команда | Описание |
|---------|----------|
| `service install [CONFIG]` | `web deps/build` при необходимости, TLS, установка unit |
| `service uninstall` | Остановить и удалить сервис |
| `service start` / `stop` / `restart` / `status` | Управление unit (вместо `systemctl`) |

## HTTPS

Интерактивно (TTY) или флаги `--no-tls`, `--tls-self-signed`, `--tls-ip`, `--ssl-certfile`, … — как в прежнем `install-server`.

## Troubleshooting

```bash
evileye status
evileye service status
journalctl --user -u evileye -n 100
evileye service uninstall
evileye service install --dry-run --no-tls
```

**Site note (this deploy):** when the working directory is `/home/user/EvilEye` (dev tree) but the unit’s `WorkingDirectory` is `/home/user/EvilEyeDeploy`, `evileye service status` may report **not installed** because it looks for `.evileye_service.json` in the current site. Prefer:

```bash
systemctl --user status evileye
systemctl --user restart evileye
```

После включения HTTPS перезапустите web-слой: `evileye service restart` / `systemctl --user restart evileye` или `evileye reload web`.

Watchdog — отдельно: `monitor/scripts/install_timer.sh` или `evileye watchdog-install`.
