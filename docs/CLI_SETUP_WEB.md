# Web UI: `evileye web`

Проверка и сборка окружения Web UI (Python API + SPA).

Полный гайд: [CLI_STACK_COMMANDS.md](CLI_STACK_COMMANDS.md).

## Подкоманды

```bash
evileye web check                 # только проверка
evileye web deps                  # pip-пакеты API
evileye web deps --scope system   # sudo pip
evileye web build                 # npm install && npm run build
evileye web build --force
evileye web refresh               # build + evileye service restart
```

## TurboJPEG

`PyTurboJPEG` ставится через pip; для нативного ускорения: `sudo apt install libturbojpeg`.

## Типовой dev-цикл

```bash
# после правки frontend или API:
evileye reload web --with-pipeline --config configs/system.json
```
