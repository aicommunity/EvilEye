# Команда `evileye setup-web`

Проверяет и при необходимости доустанавливает окружение Web UI: Python-пакеты API и собранный SPA в `evileye/api/static/`.

`evileye install-server` вызывает тот же путь автоматически, если окружение ещё не готово. Отдельный `setup-web` нужен для явной проверки (`--check`) или принудительной пересборки (`--force` / `--build`).

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

Для **локальной работы** (файлы сайта, без OS-сервиса):

```text
pip install -e .          # или pip install evileye
evileye deploy
```

Если нужен ещё и **сервер Web UI**:

```text
evileye install-server    # при необходимости сам вызовет setup-web, затем HTTPS + сервис
```

Явная проверка/пересборка SPA без установки сервиса: `evileye setup-web` / `evileye setup-web --check`.

Если нужен только Web UI/backend без запуска runtime, поднимите сервер отдельно:

```bash
evileye server --host 0.0.0.0 --port 8181 --no-reload
```

См. также [`WEB_UI_GUIDE.md`](WEB_UI_GUIDE.md), [`CLI_DEPLOY_COMMAND.md`](CLI_DEPLOY_COMMAND.md), [`CLI_SERVICE_COMMANDS.md`](CLI_SERVICE_COMMANDS.md).
