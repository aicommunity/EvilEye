# Docker deployment (GPU + CPU)

Этот гайд описывает Docker Hub-образы EvilEye и сценарий «пустая папка».

## Теги образов

| Тег | Назначение |
|-----|------------|
| `evileye/app:latest` | GPU (CUDA), последний релиз |
| `evileye/app:cpu` | CPU-only, последний релиз |
| `evileye/app:<version>` | GPU, конкретная версия (например `0.0.15`) |
| `evileye/app:<version>-cpu` | CPU, конкретная версия |

Образы ставят приложение через `pip install evileye==<version>` на момент сборки (см. build-arg `EVILEYE_VERSION`).

CI: `.github/workflows/docker-publish.yml` пушит теги на Docker Hub при GitHub Release (или `workflow_dispatch`). Нужны secrets репозитория: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`.

## Быстрый старт: пустая папка

```bash
mkdir mysite && cd mysite

docker pull evileye/app:latest

docker run --rm -v "$PWD":/site -e EVILEYE_BOOTSTRAP_IMAGE=evileye/app:latest evileye/app:latest bootstrap

docker compose up -d

export PATH="$PWD/bin:$PATH"
evileye --help
```

После bootstrap в папке появятся:

- `docker-compose.yml` (шаблон с `image: ${EVILEYE_IMAGE:-…}`)
- `.env` (`EVILEYE_IMAGE`, `POSTGRES_PASSWORD`, порты)
- `credentials.json` (пароль БД совпадает с `POSTGRES_PASSWORD`)
- `configs/single_video.json`
- `EvilEyeData/`, `videos/`, `models/`, `logs/`
- `postgres_data/`
- `bin/evileye*` (bash + Windows `.cmd`/`.ps1` host-cli wrappers)

Web UI: `http://127.0.0.1:8181`

Повторный `bootstrap` **не** затирает существующие `docker-compose.yml` / `.env`. Чтобы перезаписать: `EVILEYE_BOOTSTRAP_FORCE=1` или `bootstrap --force` (создаётся `*.bak`).

Смена `POSTGRES_PASSWORD` в `.env` **не** меняет пароль уже инициализированного Postgres volume — нужен `ALTER USER` или удаление `postgres_data/`.

## Repo layout (из исходников)

Из корня репозитория:

```bash
./docker/prepare-host-dirs.sh
make docker-up
# эквивалент:
# docker compose --project-directory . -f docker/docker-compose.yml up -d --build
```

`make docker-up` задаёт `EVILEYE_SITE_DIR` на корень репо (compose-файл лежит в `docker/`).

## Управление через CLI (native vs Docker)

| Задача | Native (systemd) | Docker Compose |
|--------|------------------|----------------|
| Статус | `evileye status` | `docker compose ps` + `docker compose exec web evileye status` |
| Перезапуск Web UI | `evileye reload web` | `docker compose restart web` |
| Перезапуск pipeline | `evileye pipeline restart CONFIG` | `docker compose restart app` |
| Production up | `evileye prod up` | `docker compose up -d` |

В контейнере `evileye service *` недоступен — роль `web`-сервиса выполняет контейнер с `restart: unless-stopped`.

## Compose по умолчанию

Bootstrap-шаблон поднимает 3 сервиса:

- `db` — Postgres (`healthcheck` + `depends_on: service_healthy`)
- `web` — `evileye server`
- `app` — `evileye run ... --no-gui`

Данные Postgres сохраняются локально в рабочей папке:

```yaml
./postgres_data:/var/lib/postgresql/data
```

## CPU-вариант

```bash
mkdir mysite-cpu && cd mysite-cpu

docker pull evileye/app:cpu
docker run --rm -v "$PWD":/site -e EVILEYE_BOOTSTRAP_IMAGE=evileye/app:cpu evileye/app:cpu bootstrap

docker compose up -d
```

Или в уже bootstrap-папке (image берётся из `.env` / переменной):

```bash
EVILEYE_IMAGE=evileye/app:cpu docker compose up -d
```

## Host CLI

После bootstrap в `bin/` лежат:

- bash-обёртки (`evileye`, …) — Linux / macOS / Git Bash / WSL
- Windows-обёртки (`evileye.cmd`, `evileye.ps1`, `EvilEye-DockerRun.ps1`) — PowerShell / cmd

Site-dir резолвится как родитель `bin/` (не путь `/site` из контейнера).

Без NVIDIA на хосте используйте CPU-образ или `EVILEYE_DOCKER_GPU_MODE=none` (иначе `--gpus all` упадёт).

Пример (Linux):

```bash
export PATH="$PWD/bin:$PATH"
evileye run configs/single_video.json --no-gui
```

Пример (Windows PowerShell):

```powershell
$env:Path = "$PWD\bin;$env:Path"
evileye --help
```

Подробности для Windows: [WINDOWS_DOCKER_DEPLOYMENT.md](WINDOWS_DOCKER_DEPLOYMENT.md) (секция Host CLI).
Глобальная установка на Windows: `docker/windows/Install-HostCli.ps1`.

## ACL / пользователи

ACL и prefs сохраняются в site-файлах (`credentials.json`, `web_users.json`), не в образе.

- bootstrap-admin видит все камеры
- новым non-admin пользователям нужно назначить `allowed_cameras`, иначе Live будет пустым

## Сборка и push образов

Из корня репозитория:

```bash
make docker-build        # evileye/app:<version> + :latest
make docker-build-cpu    # evileye/app:<version>-cpu + :cpu
make docker-push
```

Вручную:

```bash
VERSION=$(python3 -c "import re; print(re.search(r'^version\s*=\s*\"([^\"]+)\"', open('pyproject.toml', encoding='utf-8').read(), re.M).group(1))")
docker build -f docker/Dockerfile --build-arg EVILEYE_VERSION=$VERSION \
  -t evileye/app:$VERSION -t evileye/app:latest .
docker build -f docker/Dockerfile.cpu --build-arg EVILEYE_VERSION=$VERSION \
  -t evileye/app:$VERSION-cpu -t evileye/app:cpu .
docker push evileye/app:$VERSION && docker push evileye/app:latest
docker push evileye/app:$VERSION-cpu && docker push evileye/app:cpu
```

## Лицензия

GPU-образ использует базу `ultralytics/ultralytics` (AGPL). Учитывайте это при коммерческом использовании.
