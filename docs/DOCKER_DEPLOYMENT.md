# Docker deployment (GPU + CPU)

Этот гайд описывает Docker Hub-образы EvilEye и сценарий «пустая папка».

- GPU-образ: `evileye/app:latest`
- CPU-образ: `evileye/app:cpu`

Оба образа ставят приложение через `pip install evileye` (без пина версии).

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

- `docker-compose.yml`
- `credentials.json`
- `configs/single_video.json`
- `EvilEyeData/`, `videos/`, `models/`, `logs/`
- `postgres_data/`
- `bin/evileye*` (bash + Windows `.cmd`/`.ps1` host-cli wrappers)

Web UI: `http://127.0.0.1:8181`

## Важно про свежесть PyPI

Образы берут пакет из PyPI на момент сборки. Если в PyPI ещё старая версия, сборка может пройти, но поведение будет старым (например, без последних web-правок).

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

- `db` — Postgres
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

Или в уже bootstrap-папке:

```bash
EVILEYE_IMAGE=evileye/app:cpu docker compose up -d
```

## Host CLI

После bootstrap в `bin/` лежат:

- bash-обёртки (`evileye`, …) — Linux / macOS / Git Bash / WSL
- Windows-обёртки (`evileye.cmd`, `evileye.ps1`, `EvilEye-DockerRun.ps1`) — PowerShell / cmd

Site-dir резолвится как родитель `bin/` (не путь `/site` из контейнера).

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
docker build -f docker/Dockerfile -t evileye/app:latest .
docker build -f docker/Dockerfile.cpu -t evileye/app:cpu .

docker push evileye/app:latest
docker push evileye/app:cpu
```

## Лицензия

GPU-образ использует базу `ultralytics/ultralytics` (AGPL). Учитывайте это при коммерческом использовании.
