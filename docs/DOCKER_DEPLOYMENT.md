# Docker-деплой EvilEye (GPU)

Развёртывание EvilEye в контейнере на базе официального образа [Ultralytics](https://hub.docker.com/r/ultralytics/ultralytics) (PyTorch + CUDA + YOLO). Каталог данных по умолчанию лежит **на хосте** (bind-mount).

Штатный путь `pip install evileye` / `pip install -e .` **не меняется** и не зависит от этого гайда.

## Обзор режимов

| Режим | Когда использовать |
|-------|-------------------|
| **Compose** (`app` + Postgres) | Полный стек на одной машине |
| **Host CLI** | Команды `evileye …` на хосте как после pip, исполнение внутри контейнера |
| **pip на хосте** | Обычная установка без Docker (см. корневой README) |

Не ставьте одновременно pip-entry points и Docker host-cli в один `PATH` — оба создают бинарь `evileye`.

## Требования к хосту

1. Docker Engine и Docker Compose v2
2. Драйвер NVIDIA
3. [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

Проверка GPU в Docker:

```bash
docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi
```

На новых связках Docker ≥ 28.2 и nvidia-container-toolkit ≥ 1.18 Ultralytics рекомендует CDI:

```bash
docker run --rm --device nvidia.com/gpu=all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi
```

Для host-cli: `EVILEYE_DOCKER_GPU_MODE=cdi` (по умолчанию `gpus`).

## Подготовка каталогов на хосте

Из корня репозитория:

```bash
./docker/prepare-host-dirs.sh
# или: make prepare-docker-host
```

Создаются: `EvilEyeData/images`, `videos`, `models`, `configs`, `logs`, при отсутствии — `credentials.json` из `evileye/credentials_proto.json`.

### База данных и `credentials.json`

Приложение читает параметры БД **только** из `credentials.json` (ключ `database.host_name`), не из переменных `DB_HOST`.

Для стека Compose сервис Postgres называется `db`. Укажите:

```json
"database": {
  "user_name": "postgres",
  "password": "postgres",
  "database_name": "evil_eye_db",
  "host_name": "db",
  "port": 5432,
  "admin_user_name": "postgres",
  "admin_password": "postgres"
}
```

Конфиги и модели:

- скопируйте sample-конфиги в `configs/` (например из `evileye/samples_configs/`);
- положите веса в `models/` (пути в JSON относительно рабочего каталога `/opt/evileye` в Compose или `$PWD` в host-cli).

Файл `credentials.json` **обязателен** до `compose up`: Compose монтирует его как файл; если файла нет, Docker выдаст ошибку монтирования.

## Сборка образа

Базовый образ: `ultralytics/ultralytics:8.4.115` (pin в Dockerfile / compose `build.args.ULTRALYTICS_TAG`).

```bash
docker compose -f docker/docker-compose.yml build
# или: make docker-build

# другой pin base:
docker compose -f docker/docker-compose.yml build --build-arg ULTRALYTICS_TAG=8.4.116
```

Итоговое имя образа: `evileye/app:latest`.

> Лицензия базового образа Ultralytics — AGPL; EvilEye — MIT. Учитывайте это при коммерческом использовании стека.

## Запуск через Compose

```bash
./docker/prepare-host-dirs.sh
# отредактируйте credentials.json (host_name: "db") и configs/
docker compose -f docker/docker-compose.yml up --build
# или: make docker-up
```

По умолчанию:

- команда: `evileye run configs/single_video.json --no-gui`
- Web UI/API порт хоста: `8181` (`EVILEYE_HOST_PORT`)
- Postgres: `5432` (`EVILEYE_PG_PORT`)

Запуск только приложения (внешняя БД / без БД):

```bash
docker compose -f docker/docker-compose.yml up app
```

Web-сервер вручную (override command):

```bash
docker compose -f docker/docker-compose.yml run --rm -p 8181:8181 app \
  evileye server --host 0.0.0.0 --port 8181
```

## Данные на хосте (bind-mounts)

Пути относительно каталога `docker/` (то есть корень репозитория — `..`):

| Переменная | Default на хосте | В контейнере |
|------------|------------------|--------------|
| `EVILEYE_HOST_DATA` | `../EvilEyeData` | `/opt/evileye/EvilEyeData` |
| `EVILEYE_HOST_VIDEOS` | `../videos` | `/opt/evileye/videos` |
| `EVILEYE_HOST_MODELS` | `../models` | `/opt/evileye/models` |
| `EVILEYE_HOST_CONFIGS` | `../configs` | `/opt/evileye/configs` |
| `EVILEYE_HOST_LOGS` | `../logs` | `/opt/evileye/logs` |
| `EVILEYE_HOST_CREDENTIALS` | `../credentials.json` | `/opt/evileye/credentials.json` |

В контейнере задано `EVILEYE_DATA_DIR=/opt/evileye/EvilEyeData`.

Пример смены каталога данных:

```bash
export EVILEYE_HOST_DATA=/var/lib/evileye/data
mkdir -p "$EVILEYE_HOST_DATA"
docker compose -f docker/docker-compose.yml up
```

## Host CLI (команды на хосте → контейнер)

Opt-in: **не** входит в `pip install`. Ставит тонкие обёртки в `~/.local/bin` (или `PREFIX`).

```bash
docker compose -f docker/docker-compose.yml build   # образ должен существовать
./docker/install-host-cli.sh
# или: make install-docker-cli

evileye --help
evileye run configs/single_video.json --no-gui
evileye-process --config configs/single_video.json
```

Удаление обёрток (pip не затрагивается):

```bash
./docker/uninstall-host-cli.sh
# или: make uninstall-docker-cli
```

### Как работает

- Обёртки вызывают `evileye-docker-run.sh`, который делает `docker run` с образом `evileye/app:latest`.
- Монтируется текущий каталог: `-v "$PWD:$PWD" -w "$PWD"` — относительные пути в конфигах совпадают с хостом.
- GPU: `--gpus all` или CDI (`EVILEYE_DOCKER_GPU_MODE=cdi`).
- Переменные: `EVILEYE_DOCKER_IMAGE`, `EVILEYE_DOCKER_EXTRA_ARGS`, `EVILEYE_DATA_DIR`.

### Ограничения host-cli

- На хосте нет `import evileye` / `pip show evileye` — только CLI-имена.
- GUI (`--gui`) через контейнер не поддерживается официально.
- Нужен заранее собранный образ.
- Файлы вне `$PWD` (и не попавшие в mount) в контейнере недоступны.
- При конфликте с pip install install-скрипт выводит предупреждение.

## GPU: проверка

```bash
docker run --rm --gpus all evileye/app:latest \
  python -c "import torch; print(torch.__version__, torch.cuda.is_available())"

docker run --rm --gpus all evileye/app:latest evileye info
```

## Запуск без Compose

```bash
docker run --rm --gpus all --ipc=host \
  -v "$PWD/EvilEyeData:/opt/evileye/EvilEyeData" \
  -v "$PWD/videos:/opt/evileye/videos" \
  -v "$PWD/models:/opt/evileye/models" \
  -v "$PWD/configs:/opt/evileye/configs" \
  -v "$PWD/logs:/opt/evileye/logs" \
  -v "$PWD/credentials.json:/opt/evileye/credentials.json" \
  -e EVILEYE_DATA_DIR=/opt/evileye/EvilEyeData \
  -p 8181:8181 \
  evileye/app:latest \
  evileye run configs/single_video.json --no-gui
```

## Postgres: compose vs внешняя БД

| Вариант | `database.host_name` |
|---------|----------------------|
| Сервис `db` в compose | `db` |
| Postgres на хосте | `host.docker.internal` (если поддерживается) или IP хоста в docker-сети |
| Без БД | отключите `use_database` в конфиге / работайте с JSON в `EvilEyeData` |

Пароль и имя БД по умолчанию в compose: `postgres` / `evil_eye_db`.

## Отличия от штатного pip-деплоя

| | pip install | Docker |
|--|-------------|--------|
| GPU-стек | ставите на хост сами | уже в образе Ultralytics |
| Команда `evileye` | entry point пакета | контейнер или host-cli обёртка |
| Данные | `./EvilEyeData` на хосте | то же через bind-mount |
| БД | localhost / свой Postgres | сервис `db` или внешний |
| GUI | поддерживается на хосте | headless по умолчанию |
| Watchdog systemd | `evileye deploy` + monitor | по желанию на хосте отдельно |

## Windows

Host-cli bash scripts (`install-host-cli.sh`, `prepare-host-dirs.sh`) are **Linux/WSL-only**.

On Windows use Docker Desktop + PowerShell:

- [WINDOWS_DOCKER_DEPLOYMENT.md](WINDOWS_DOCKER_DEPLOYMENT.md)
- `docker/windows/Install-EvilEye.ps1`, `Prepare-HostDirs.ps1`, `Install-Watchdog.ps1`

Compose includes services `app` (pipeline), `web` (API/UI on :8181), and `db`, all with `restart: unless-stopped`.

## Troubleshooting

- **Compose: error mounting credentials.json** — сначала `./docker/prepare-host-dirs.sh` (Linux) или `docker/windows/Prepare-HostDirs.ps1` (Windows).
- **CUDA unavailable** — драйвер, toolkit, флаги `--gpus` / CDI, `nvidia-smi` в тестовом контейнере.
- **Нет видео / NVDEC** — в compose уже есть `NVIDIA_DRIVER_CAPABILITIES=compute,utility,video`; при необходимости software decode: `EVILEYE_GST_FORCE_SW_DECODER=1`.
- **pip и docker-cli конфликтуют** — `which -a evileye`; удалите один из способов (`uninstall-docker-cli` или `pip uninstall evileye`).
- **Огромный образ** — ожидаемо (база Ultralytics/PyTorch CUDA); веса моделей в образ не копируются (см. `.dockerignore`).

## Связанные файлы

- [`docker/Dockerfile`](../docker/Dockerfile)
- [`docker/docker-compose.yml`](../docker/docker-compose.yml)
- [`docker/install-host-cli.sh`](../docker/install-host-cli.sh)
- [`docker/prepare-host-dirs.sh`](../docker/prepare-host-dirs.sh)
- [`docker/windows/`](../docker/windows/)
- [Windows Docker](WINDOWS_DOCKER_DEPLOYMENT.md)
- [Команда deploy](CLI_DEPLOY_COMMAND.md)
- [Настройка БД](DATABASE_SETUP_GUIDE.md)
