# Команда `evileye setup-web`

Проверяет и при необходимости доустанавливает окружение Web UI: Python-пакеты API и собранный SPA в `evileye/api/static/`.

## Зачем

- `pip install evileye` уже тянет FastAPI/uvicorn/`PyTurboJPEG`, но:
  - SPA может отсутствовать в окружении → нужна сборка frontend;
  - для реального TurboJPEG нужна системная `libturbojpeg` (иначе fallback на OpenCV).
- Команда сначала **проверяет**, затем при необходимости ставит недостающее.

## Использование

```bash
evileye setup-web                 # check + fix
evileye setup-web --check         # только проверка (exit 1 при проблемах)
evileye setup-web --scope user    # pip --user (по умолчанию)
evileye setup-web --scope system  # sudo pip (спросит подтверждение)
evileye setup-web --build         # принудительно npm install && npm run build
evileye setup-web --no-build      # не трогать frontend
evileye setup-web --force         # пересобрать SPA / доустановить missing Python pkgs
```

## Что проверяется

| Check | Смысл |
|-------|--------|
| `fastapi` / `uvicorn` / `pydantic` / `itsdangerous` | Python API |
| `turbojpeg` import | пакет PyTurboJPEG |
| `TurboJPEG()` | нативная `libturbojpeg.so` |
| `static` | `evileye/api/static/index.html` + `assets/` |
| `node` / `npm` | нужны только для сборки SPA |
| `frontend_sources` | `evileye/api/frontend/package.json` |

## Pip scope vs npm

- `--scope user|system` относится **только к pip**.
- `npm install` всегда локальный в `evileye/api/frontend/node_modules` (без глобальной установки).

## TurboJPEG / libjpeg-turbo

`PyTurboJPEG` — pure-Python wheel: **`pip install` проходит без системной библиотеки**.

Без `libturbojpeg`:

- установка OK;
- EvilEye стартует;
- `TurboJPEG()` падает → encoder переключается на OpenCV (медленнее preview).

Debian/Ubuntu:

```bash
sudo apt install libturbojpeg
```

## Типовой сценарий сайта

```text
pip install -e .          # или pip install evileye
sudo apt install libturbojpeg   # рекомендуется
evileye setup-web
evileye deploy
evileye run configs/my.json --no-gui
```

См. также [`WEB_UI_GUIDE.md`](WEB_UI_GUIDE.md), [`CLI_DEPLOY_COMMAND.md`](CLI_DEPLOY_COMMAND.md).
