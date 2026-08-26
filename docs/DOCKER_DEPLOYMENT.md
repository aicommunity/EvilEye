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
- `bin/evileye*` (host-cli wrappers)

Web UI: `http://127.0.0.1:8181`

## Важно про свежесть PyPI

Образы берут пакет из PyPI на момент сборки. Если в PyPI ещё старая версия, сборка может пройти, но поведение будет старым (например, без последних web-правок).

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

`bin/evileye` и связанные команды на хосте запускают контейнер под капотом.

Пример:

```bash
export PATH="$PWD/bin:$PATH"
evileye run configs/single_video.json --no-gui
```

Можно запускать из любой папки, если wrapper экспортирует `EVILEYE_DOCKER_SITE_DIR` (bootstrap делает это автоматически).

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
