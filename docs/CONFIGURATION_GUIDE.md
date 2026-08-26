# Руководство по конфигурациям EvilEye

Данное руководство описывает структуру конфигурационных файлов системы EvilEye и содержит ссылки на реальные рабочие примеры конфигураций.

> **См. также**: [Архитектура Pipeline](PIPELINE_ARCHITECTURE.md) - Для понимания архитектуры pipeline классов и их конфигураций

## Быстрый старт

### Получение примеров конфигураций

Для получения готовых примеров конфигураций выполните:

```bash
evileye deploy-samples
```

Эта команда создаст папку `configs/` с примерами конфигураций и папку `videos/` с тестовыми видео файлами.

### Создание новой конфигурации

Для создания новой конфигурации используйте:

```bash
evileye create my_config --sources 2 --source-type video_file
```

Подробнее о создании конфигураций см. [CREATE_SCRIPT_README.md](CREATE_SCRIPT_README.md).

## Файл credentials.json

Файл `credentials.json` используется для хранения чувствительных данных (паролей, токенов доступа) отдельно от основных конфигурационных файлов. Это позволяет не хранить пароли в конфигурациях, которые могут попасть в систему контроля версий.

### Создание credentials.json

Файл `credentials.json` создается автоматически при выполнении команды:

```bash
evileye deploy
```

или

```bash
evileye deploy-samples
```

Эта команда копирует шаблон `credentials_proto.json` в `credentials.json` в текущей рабочей директории.

### Структура credentials.json

Файл содержит две основные секции:

```json
{
  "sources": {
    "rtsp://camera1.example.com": {
      "username": "camera_user",
      "password": "camera_password"
    },
    "rtsp://camera2.example.com": {
      "username": "admin",
      "password": "admin123"
    }
  },
  "database": {
    "user_name": "postgres",
    "password": "your_db_password",
    "database_name": "evil_eye_db",
    "host_name": "localhost",
    "port": 5432,
    "admin_user_name": "postgres",
    "admin_password": "your_admin_password"
  }
}
```

### Секция web_auth

Для веб-интерфейса и web API можно включить cookie-based аутентификацию. Пользователи хранятся в `credentials.json`, чтобы не попадать в обычные CRUD-конфиги веб-интерфейса.

```json
{
  "web_auth": {
    "enabled": true,
    "session_secret": "change-me",
    "secure_cookies": false,
    "internal_token": "",
    "users": [
      {
        "username": "admin",
        "password": "change-me",
        "password_hash": "",
        "role": "admin",
        "disabled": false
      },
      {
        "username": "operator",
        "password": "operator-pass",
        "password_hash": "",
        "role": "user",
        "disabled": false
      },
      {
        "username": "analyst",
        "password": "analyst-pass",
        "password_hash": "",
        "role": "power_user",
        "disabled": false
      }
    ]
  }
}
```

**Параметры**:

| Параметр | Тип | Описание |
|----------|-----|----------|
| `enabled` | boolean | Включить проверку пользователей для `/api/v1/*` |
| `session_secret` | string | Ключ подписи session cookie |
| `secure_cookies` | boolean | Выставлять cookie только по HTTPS |
| `internal_token` | string | Отдельный токен для внутренних endpoint'ов `/api/v1/internal/*` |
| `users` | array | Список пользователей веб-интерфейса |
| `users[].username` | string | Имя пользователя |
| `users[].password` | string | Временный открытый пароль для bootstrap-сценариев |
| `users[].password_hash` | string | Предпочтительный формат: `pbkdf2_sha256$iterations$salt$hash` |
| `users[].role` | string | Роль: `user`, `power_user` или `admin` |
| `users[].disabled` | boolean | Отключение пользователя без удаления |

**Рекомендации**:

1. Для production используйте `password_hash`, а не открытый `password`.
2. Для HTTPS включайте `secure_cookies=true`.
3. Для внутренних вызовов между процессами задавайте `internal_token` (при `enabled=true` пустой токен запрещён — сервер сгенерирует его при старте).
4. `user` подходит для live-мониторинга камер.
5. `power_user` предназначен для просмотра предметных журналов системы и технических логов.
6. `admin` предназначен для настройки и управления системой.
7. Не оставляйте дефолтный `session_secret` (`evileye-dev-session-secret` / `change-me`) — при обнаружении слабого значения сервер заменит его на криптостойкий.
8. Первый bootstrap admin получает одноразовый случайный пароль (или `EVILEYE_BOOTSTRAP_ADMIN_PASSWORD`); пароль пишется только в лог запуска. Смените его через UI (**Настройки** → смена пароля) или `POST /api/v1/auth/change-password` / `PATCH /api/v1/users/admin`.
9. Production checklist: `enabled=true`, `secure_cookies=true`, HTTPS, явный `EVILEYE_CORS_ALLOW_ORIGINS`, заданный `internal_token`, секция `protection` для rate-limit/IP ban (см. ниже).

**Два хранилища пользователей**:

| Хранилище | Файл | Кто |
|-----------|------|-----|
| Bootstrap / ручной | `credentials.json` → `web_auth.users` | username (например `admin`) |
| Регистрация / UI create | `web_users.json` | email + status pending/approved |

Страница `/admin/users` и `GET /api/v1/users` показывают **оба** списка (`source: credentials|store`). Логин объединяет оба источника.

**Camera ACL и prefs** (оба store):

```json
{
  "allowed_cameras": ["Cam1", "Cam2"],
  "prefs": {
    "visible_cameras": null,
    "lang": "ru",
    "date_format": "DD-MM-YYYY"
  }
}
```

- `allowed_cameras`: список `source_name`. Пустой / отсутствующий у non-admin → **нет доступа к камерам**. Роль `admin` всегда видит все.
- `prefs.visible_cameras`: `null` = все из ACL; явный список = пересечение с ACL для списков Live/Playback/Events.
- После апгрейда назначьте камеры пользователям в `/admin/users` (иначе старые user-аккаунты не увидят камер).

### Секция web_auth.protection

Защита от brute-force и флуда с автобаном IP. Управление банами: UI `/admin/bans` (permission `bans:manage`) или API `/api/v1/bans`.

```json
"protection": {
  "enabled": true,
  "trust_proxy": false,
  "trusted_proxy_ips": ["127.0.0.1"],
  "login_max_failures": 10,
  "login_window_sec": 300,
  "login_ban_sec": 1800,
  "register_max_per_window": 5,
  "register_window_sec": 600,
  "register_ban_sec": 3600,
  "global_max_requests": 120,
  "global_window_sec": 60,
  "global_ban_sec": 600,
  "whitelist_ips": ["127.0.0.1", "::1"]
}
```

При `web_auth.enabled=true` protection по умолчанию включена. Env: `EVILEYE_TRUST_PROXY=1`, `EVILEYE_PROTECTION_ENABLED=0` (отладка). Баны хранятся в `web_ip_bans.json` (не коммитить).

**Multi-worker:** счётчики rate limit живут в памяти процесса. Для EvilEye типичен один uvicorn worker; при нескольких workers автобан всё равно пишется в `web_ip_bans.json`, но пороги могут срабатывать позже. Sticky sessions / один worker — рекомендуемый режим; общий Redis store — out of scope.

### Server module и схемы запуска

Секция `web_auth.internal_token` используется не только для защиты внутренних endpoint'ов,
но и для обмена данными между runtime и server module в многопроцессных сценариях.

Актуальные схемы того, кто кого запускает и как передаются preview-кадры, приведены в
документе [`MULTIPROCESSING.md`](MULTIPROCESSING.md), раздел
`Веб-сервер: актуальные схемы запуска`.

Кратко:

- `evileye run` + `server.enabled: true` — основной сценарий, где система владеет runtime, а server module работает как её web/API-слой;
- `evileye server` — служебный server-first сценарий, где runtime запускается через REST API;
- если server уже запущен отдельно, runtime не поднимает второй web-server, а отправляет preview в существующий server module через внутренний API.

### Журналы и логи в web/API

В терминах EvilEye это разные сущности:

- `журналы` — предметные данные системы, например журналы событий и объектов, которые читаются через БД и domain services;
- `логи` — технические текстовые логи процессов сервера и runtime, используемые для диагностики и отладки.

В web-ui и API эти сущности следует рассматривать и настраивать отдельно: доступ к журналам нужен для анализа результатов работы конфигурации, а доступ к логам — для эксплуатационной диагностики.

### HTTPS для web API

Предпочтительный путь без внешнего proxy — интерактивный шаг `evileye install-server` после `evileye deploy` (самоподпись с SAN IP/DNS или существующие PEM). Сертификаты пишутся в `certs/`, пути — в `server.ssl_certfile` / `server.ssl_keyfile`.

Если публичный HTTPS даёт **Traefik** (или другой reverse-proxy), EvilEye за ним должен слушать **HTTP** на 8181 (пустые `ssl_*`), с `public_base_url` = публичный `https://…`, `trust_proxy` и `secure_cookies: true`. Подробно: [WEB_UI_REVERSE_PROXY.md](WEB_UI_REVERSE_PROXY.md). Не проксируйте Traefik → HTTPS uvicorn (double-TLS).

Порт по умолчанию остаётся **8181** (TLS на том же порту, если включён на uvicorn). HTTP и HTTPS одновременно на одном порту uvicorn не умеет.

Веб-сервер также принимает TLS напрямую:

```bash
evileye server --host 0.0.0.0 --port 8181 --ssl-certfile ./certs/server.crt --ssl-keyfile ./certs/server.key
```

`evileye run` с `server.enabled: true` читает те же `ssl_*` из конфига пайплайна / `configs/system.json`.

Приоритет путей: CLI `--ssl-*` → env `EVILEYE_SSL_CERTFILE` / `EVILEYE_SSL_KEYFILE` → `server.ssl_*`. Относительные пути — от корня сайта.

При наличии TLS cookie `Secure` включается автоматически (`web_auth.secure_cookies`). **HSTS не включается** вместе с cookies: только `server.hsts: true` или `EVILEYE_HSTS=1`. Для LAN self-signed HSTS опасен (браузер может на год запретить HTTP). Включайте HSTS только с импортированным CA или публично доверенным сертификатом.

Доступ не с localhost: задайте origins явно, например  
`EVILEYE_CORS_ALLOW_ORIGINS=https://192.168.1.50:8181,https://evileye.lan:8181`.  
Если включён `EVILEYE_ALLOWED_HOSTS`, перечислите хосты без схемы: `192.168.1.50,evileye.lan,127.0.0.1`.

`server.public_base_url` (в credentials или в `configs/system.json`) задаёт публичный URL UI/API; wizard при самоподписи пишет `https://<первый-dns-или-ip>:8181`. Relay runtime→API использует `https://127.0.0.1:{port}` и локальный CA (`certs/ca.crt` / `EVILEYE_SSL_CAFILE`).

При использовании HTTPS рекомендуется:

1. Включить `web_auth.enabled=true`
2. Оставить `secure_cookies` авто при TLS (или явно `true`)
3. Ограничить `EVILEYE_CORS_ALLOW_ORIGINS` конкретными origin вместо `*`
4. Импортировать `certs/ca.crt` на клиентах (для самоподписи)

### Секция sources

Секция `sources` содержит учетные данные для IP камер. Каждый ключ соответствует URL камеры из конфигурации источника.

**Параметры**:

| Параметр | Тип | Описание |
|----------|-----|----------|
| `username` | string | Имя пользователя для доступа к камере |
| `password` | string | Пароль для доступа к камере |

**Пример использования**:

Если в конфигурации источника указан:
```json
{
  "source": "IpCamera",
  "camera": "rtsp://192.168.1.100:554/stream1",
  "source_ids": [0],
  "source_names": ["Camera1"]
}
```

И в `credentials.json` есть запись:
```json
{
  "sources": {
    "rtsp://192.168.1.100:554/stream1": {
      "username": "admin",
      "password": "secret123"
    }
  }
}
```

То система автоматически использует эти учетные данные для подключения к камере, даже если они не указаны явно в конфигурации источника.

**Приоритет учетных данных**:

1. **Учетные данные в конфигурации источника** (наивысший приоритет)
   ```json
   {
     "source": "IpCamera",
     "camera": "rtsp://192.168.1.100:554/stream1",
     "username": "config_user",
     "password": "config_pass"
   }
   ```

2. **Учетные данные из credentials.json** (используются, если не указаны в конфигурации)
   ```json
   {
     "sources": {
       "rtsp://192.168.1.100:554/stream1": {
         "username": "cred_user",
         "password": "cred_pass"
       }
     }
   }
   ```

3. **Учетные данные из URL** (используются, если не указаны нигде)
   ```
   rtsp://user:pass@192.168.1.100:554/stream1
   ```

### Секция database

Секция `database` содержит учетные данные для подключения к базе данных PostgreSQL.

**Параметры**:

| Параметр | Тип | Описание |
|----------|-----|----------|
| `user_name` | string | Имя пользователя базы данных |
| `password` | string | Пароль пользователя базы данных |
| `database_name` | string | Имя базы данных |
| `host_name` | string | Хост базы данных |
| `port` | int | Порт базы данных |
| `admin_user_name` | string | Имя администратора базы данных (для создания БД) |
| `admin_password` | string | Пароль администратора базы данных |

**Приоритет настроек базы данных**:

1. **Настройки в секции `database` основной конфигурации** (наивысший приоритет)
2. **Настройки из `credentials.json`** (используются как значения по умолчанию)
3. **Значения по умолчанию** (hardcoded в коде)

**Пример**:

Если в основной конфигурации указано:
```json
{
  "database": {
    "database_name": "my_custom_db",
    "host_name": "db.example.com"
  }
}
```

А в `credentials.json`:
```json
{
  "database": {
    "user_name": "evileye_user",
    "password": "secret_password",
    "database_name": "evil_eye_db",
    "host_name": "localhost",
    "port": 5432
  }
}
```

То система использует:
- `database_name`: `"my_custom_db"` (из конфигурации)
- `host_name`: `"db.example.com"` (из конфигурации)
- `user_name`: `"evileye_user"` (из credentials.json)
- `password`: `"secret_password"` (из credentials.json)
- `port`: `5432` (из credentials.json)

### Безопасность

**Важно**: Файл `credentials.json` содержит чувствительные данные и **не должен** попадать в систему контроля версий.

**Рекомендации**:

1. **Добавьте `credentials.json` в `.gitignore`**:
   ```gitignore
   credentials.json
   ```

2. **Используйте `credentials_proto.json` как шаблон**:
   - Файл `credentials_proto.json` находится в репозитории и содержит пример структуры
   - При `evileye deploy` он копируется в `credentials.json`
   - Каждый пользователь заполняет свои реальные учетные данные

3. **Храните файл в безопасном месте**:
   - Ограничьте права доступа к файлу: `chmod 600 credentials.json`
   - Не передавайте файл по незащищенным каналам связи
   - Используйте переменные окружения или менеджеры секретов для production окружений

4. **Для production**:
   - Рассмотрите использование переменных окружения
   - Используйте системы управления секретами (HashiCorp Vault, AWS Secrets Manager и т.д.)
   - Регулярно меняйте пароли

### Влияние на конфигурации

Файл `credentials.json` влияет на конфигурации следующим образом:

1. **Автоматическое заполнение учетных данных камер**:
   - Если в конфигурации источника не указаны `username` и `password`, система ищет их в `credentials.json` по ключу `camera` URL
   - Это позволяет не хранить пароли в конфигурационных файлах

2. **Значения по умолчанию для базы данных**:
   - Параметры из `credentials.json` используются как значения по умолчанию для секции `database`
   - Они могут быть переопределены в основной конфигурации

3. **Упрощение управления**:
   - Один файл `credentials.json` может использоваться для всех конфигураций в проекте
   - Не нужно дублировать учетные данные в каждом конфигурационном файле

### Примеры использования

#### Пример 1: Использование credentials.json для IP камер

**Конфигурация** (`configs/surveillance.json`):
```json
{
  "pipeline": {
    "sources": [
      {
        "source": "IpCamera",
        "camera": "rtsp://192.168.1.100:554/stream1",
        "source_ids": [0],
        "source_names": ["Main Camera"]
      }
    ]
  }
}
```

**credentials.json**:
```json
{
  "sources": {
    "rtsp://192.168.1.100:554/stream1": {
      "username": "admin",
      "password": "secure_password"
    }
  }
}
```

Система автоматически использует учетные данные из `credentials.json` для подключения к камере.

#### Пример 2: Переопределение учетных данных в конфигурации

**Конфигурация** (`configs/surveillance.json`):
```json
{
  "pipeline": {
    "sources": [
      {
        "source": "IpCamera",
        "camera": "rtsp://192.168.1.100:554/stream1",
        "username": "override_user",
        "password": "override_pass",
        "source_ids": [0],
        "source_names": ["Main Camera"]
      }
    ]
  }
}
```

В этом случае используются учетные данные из конфигурации (`override_user` / `override_pass`), а не из `credentials.json`.

#### Пример 3: Использование credentials.json для базы данных

**Конфигурация** (`configs/surveillance.json`):
```json
{
  "database": {
    "database_name": "my_surveillance_db"
  }
}
```

**credentials.json**:
```json
{
  "database": {
    "user_name": "evileye_user",
    "password": "db_password",
    "host_name": "localhost",
    "port": 5432
  }
}
```

Система использует:
- `database_name`: `"my_surveillance_db"` (из конфигурации)
- `user_name`: `"evileye_user"` (из credentials.json)
- `password`: `"db_password"` (из credentials.json)
- `host_name`: `"localhost"` (из credentials.json)
- `port`: `5432` (из credentials.json)

## Базовая структура конфигурации

Конфигурационный файл EvilEye представляет собой JSON файл со следующей структурой:

```json
{
  "pipeline": {
    "pipeline_class": "PipelineSurveillance",
    "sources": [...],
    "detectors": [...],
    "trackers": [...],
    "mc_trackers": [...]
  },
  "controller": {...},
  "server": {...},
  "record": {...},
  "objects_handler": {...},
  "events_detectors": {...},
  "database": {...},
  "visualizer": {...},
  "storage_monitor": {...}
}
```

**Важно**: Структура конфигурации зависит от выбранного класса pipeline. Данное руководство описывает конфигурацию для `PipelineSurveillance`. Для других классов pipeline (например, `PipelineCapture`) структура может отличаться.

Секции `server` и `record` присутствуют в актуальных samples (`evileye/samples_configs/`) с `enabled: false` по умолчанию — включите их явно для web UI и записи. Production-like эталон: [`configs/poly-cameras-gst.json`](../configs/poly-cameras-gst.json).

## Примеры конфигураций

Все примеры конфигураций находятся в папке `evileye/samples_configs/` и могут быть использованы как шаблоны для создания собственных конфигураций.

### Базовые примеры

#### Один видео файл

**Файл**: [single_video.json](../evileye/samples_configs/single_video.json)

Простая конфигурация для обработки одного видео файла:
- Один источник видео (`VideoFile`)
- YOLO детектор (yolo11n.pt)
- BoTSORT трекер
- Межкамерный трекинг отключен
- База данных включена

**Использование**:
```bash
evileye run configs/single_video.json
```

#### IP камера

**Файл**: [single_ip_camera.json](../evileye/samples_configs/single_ip_camera.json)

Конфигурация для работы с одной IP камерой:
- Один источник IP камеры (`IpCamera`)
- RTSP поток с аутентификацией
- YOLO детектор
- BoTSORT трекер
- База данных включена

**Использование**:
```bash
evileye run configs/single_ip_camera.json
```

**Примечание**: Перед использованием обновите URL камеры и учетные данные в файле конфигурации или в `credentials.json`.

#### Несколько видео с межкамерным трекингом

**Файл**: [multi_videos.json](../evileye/samples_configs/multi_videos.json)

Конфигурация для обработки нескольких видео файлов с межкамерным трекингом:
- Два источника видео (`VideoFile`)
- Отдельные детекторы для каждого источника
- Отдельные трекеры для каждого источника
- Межкамерный трекинг включен
- База данных включена

**Использование**:
```bash
evileye run configs/multi_videos.json
```

### Примеры с разными детекторами

#### RT-DETR детектор

**Файл**: [single_video_rtdetr.json](../evileye/samples_configs/single_video_rtdetr.json)

Конфигурация с использованием RT-DETR (Real-Time Detection Transformer) детектора:
- Один видео файл
- RT-DETR детектор (rtdetr-l.pt)
- Высокая точность детекции
- Transformer архитектура

**Файл**: [multi_videos_rtdetr.json](../evileye/samples_configs/multi_videos_rtdetr.json)

Тот же детектор для нескольких видео с межкамерным трекингом.

#### RF-DETR детектор

**Файл**: [single_video_rfdetr.json](../evileye/samples_configs/single_video_rfdetr.json)

Конфигурация с использованием RF-DETR (Roboflow Detection Transformer) детектора:
- Один видео файл
- RF-DETR детектор (rfdetr-nano)
- Оптимизированная transformer архитектура
- Баланс скорости и точности

### Примеры с разными бэкендами

#### GStreamer бэкенд

**Файл**: [single_video_gstreamer.json](../evileye/samples_configs/single_video_gstreamer.json)

Конфигурация с использованием GStreamer для захвата видео:
- Один видео файл
- GStreamer бэкенд (`VideoCaptureGStreamer`)
- Улучшенная производительность
- Поддержка аппаратного декодирования

**Файл**: [ip_camera_gstreamer.json](../evileye/samples_configs/ip_camera_gstreamer.json)

IP камера с GStreamer бэкендом для оптимальной работы с RTSP потоками.

**Файл**: [usb_camera_gstreamer.json](../evileye/samples_configs/usb_camera_gstreamer.json)

USB камера с GStreamer бэкендом.

Подробнее о GStreamer см. [VideoCaptureGStreamer_Usage.md](VideoCaptureGStreamer_Usage.md).

### Специальные примеры

#### Видео с разделением

**Файл**: [single_video_split.json](../evileye/samples_configs/single_video_split.json)

Конфигурация для обработки одного видео файла с разделением на несколько областей:
- Один видео файл
- Разделение на 2 области (`split: true`, `num_split: 2`)
- Отдельные детекторы и трекеры для каждой области
- Координаты областей в `src_coords`

**Особенности**:
- Позволяет обрабатывать несколько камер из одного видео файла
- Каждая область имеет свой `source_id`
- Полезно для видео с несколькими камерами в одном файле

#### Конфигурация с атрибутами

**Файл**: [single_video_with_attributes.json](../evileye/samples_configs/single_video_with_attributes.json)

Конфигурация с детекцией и трекингом атрибутов объектов:
- Один видео файл
- Детекция атрибутов (каска, рюкзак и т.д.)
- Настройки детекции атрибутов в секции `objects_handler.attributes_detection`
- RT-DETR детектор для атрибутов

Подробнее о системе детекции атрибутов см. [ATTRIBUTES_DETECTION_README.md](ATTRIBUTES_DETECTION_README.md).

#### PipelineCapture

**Файл**: [pipeline_capture.json](../evileye/samples_configs/pipeline_capture.json)

Упрощенная конфигурация для класса `PipelineCapture`:
- Простой захват видео без детекции и трекинга
- Минимальная конфигурация
- Только секции `pipeline` и `controller`
- База данных отключена

Подробнее о PipelineCapture см. [PIPELINE_ARCHITECTURE.md](PIPELINE_ARCHITECTURE.md#pipelinecapture).

### Последовательности изображений

#### JPEG последовательность

**Файл**: [image_sequence_gstreamer_jpg.json](../evileye/samples_configs/image_sequence_gstreamer_jpg.json)

Конфигурация для обработки последовательности JPEG изображений через GStreamer:
- Обработка JPEG файлов как видео потока
- GStreamer бэкенд
- Поддержка папок с изображениями

#### Папка с изображениями

**Файл**: [image_sequence_gstreamer_folder.json](../evileye/samples_configs/image_sequence_gstreamer_folder.json)

Конфигурация для обработки всех изображений в папке:
- Автоматическая обработка всех изображений в указанной папке
- GStreamer бэкенд
- Поддержка различных форматов изображений

Подробнее о последовательностях изображений см. [ImageSequence_GStreamer_Usage.md](ImageSequence_GStreamer_Usage.md).

## Описание секций конфигурации

### Секция `pipeline`

Основная секция, определяющая pipeline обработки видео.

#### `pipeline_class`

Тип pipeline класса для использования:
- `PipelineSurveillance` - Полнофункциональная surveillance pipeline (по умолчанию)
- `PipelineCapture` - Упрощенная pipeline для захвата видео

#### `sources`

Массив конфигураций видео источников. Каждый источник определяет:
- Тип источника (`IpCamera`, `VideoFile`, `Device`)
- Путь к видео или URL камеры
- Параметры разделения (если требуется)
- Идентификаторы и имена источников

**Пример**:
```json
"sources": [
  {
    "camera": "videos/planes_sample.mp4",
    "source": "VideoFile",
    "split": false,
    "num_split": 0,
    "src_coords": [0],
    "source_ids": [0],
    "source_names": ["Cam1"]
  }
]
```

**Параметры источника**:

| Параметр | Тип | Описание | Обязательный |
|----------|-----|----------|--------------|
| `source` | string | Тип источника: `IpCamera`, `VideoFile`, `Device` | Да |
| `camera` | string/int | URL камеры, путь к файлу или индекс устройства | Да |
| `source_ids` | array | Уникальные идентификаторы источников | Да |
| `source_names` | array | Имена источников для отображения | Да |
| `split` | boolean | Включить разделение источника | Нет (по умолчанию: `false`) |
| `num_split` | int | Количество областей при разделении | Нет |
| `src_coords` | array | Координаты областей `[x, y, width, height]` | Нет |
| `loop_play` | boolean | Зацикливать видео файлы | Нет (по умолчанию: `true`) |
| `desired_fps` | int/null | Желаемый FPS для источника | Нет |
| `type` | string | Тип бэкенда: `VideoCaptureGStreamer` для GStreamer | Нет |
| `apiPreference` | string | Для GStreamer: `CAP_GSTREAMER` | Нет |
| `gstreamer_available` | boolean | Явно включить GStreamer-путь capture | Нет |
| `username` | string | Имя пользователя для IP камеры | Нет |
| `password` | string | Пароль для IP камеры | Нет |

**GStreamer:** если указан `"type": "VideoCaptureGStreamer"`, задайте также `"apiPreference": "CAP_GSTREAMER"` и `"gstreamer_available": true`. Иначе возможен fallback на OpenCV.

**Split-источники:** `split` / `num_split` / `src_coords` / несколько `source_names` на одном физическом потоке. На диск пишется один набор файлов в папку `"-".join(source_names)` с префиксом `source_names[0]`; web playback кропает по `src_coords` (см. [`WEB_UI_GUIDE.md`](WEB_UI_GUIDE.md)).

**Примеры типов источников**:

- **IP Camera**: [single_ip_camera.json](../evileye/samples_configs/single_ip_camera.json)
- **Video File**: [single_video.json](../evileye/samples_configs/single_video.json)
- **USB Camera**: [usb_camera_gstreamer.json](../evileye/samples_configs/usb_camera_gstreamer.json)
- **Split Video**: [single_video_split.json](../evileye/samples_configs/single_video_split.json)

#### `detectors`

Массив конфигураций детекторов объектов. Каждый детектор определяет:
- Модель детекции (YOLO, RT-DETR, RF-DETR)
- Источники для обработки
- Классы объектов для детекции
- Параметры детекции (confidence, inference_size и т.д.)

**Пример YOLO детектора**:
```json
"detectors": [
  {
    "model": "models/yolo11n.pt",
    "classes": [0, 1, 24, 25, 63, 66, 67],
    "source_ids": [0],
    "roi": [[]],
    "vid_stride": 1,
    "num_detection_threads": 1
  }
]
```

**Пример RT-DETR детектора**:
```json
"detectors": [
  {
    "type": "ObjectDetectorRtdetr",
    "model": "models/rtdetr-l.pt",
    "classes": [0, 1, 24, 25, 63, 66, 67],
    "source_ids": [0],
    "inference_size": 640,
    "conf": 0.25,
    "roi": [[]],
    "vid_stride": 1,
    "num_detection_threads": 1
  }
]
```

**Параметры детектора**:

| Параметр | Тип | Описание | По умолчанию |
|----------|-----|----------|--------------|
| `type` | string | `ObjectDetectorYolo` (YOLO, рекомендуется), `ObjectDetectorRtdetr`, `ObjectDetectorRfdetr`; **deprecated:** `ObjectDetectorYoloMp` | YOLO: often omitted (default factory) |
| `model` | string | Путь к модели детектора | `models/yolo11n.pt` |
| `source_ids` | array | Идентификаторы источников для обработки | - |
| `classes` | array | Классы объектов COCO для детекции | `[0, 1, 24, 25, 63, 66, 67]` |
| `inference_size` | int | Размер входного изображения для модели | `640` |
| `conf` | float | Порог уверенности детекции | `0.25` |
| `roi` | array | Области интереса (Regions of Interest) | `[[]]` |
| `vid_stride` | int | Шаг обработки кадров | `1` |
| `num_detection_threads` | int | Количество потоков для детекции | `1` |
| `execution_mode` | string | `"thread"` — inference в процессе controller; `"process"` — child worker + feed/drain (`MpAsyncBridge`) | `"process"` (если ключ опущен, см. `DEFAULT_EXECUTION_MODE`) |

**Primary path (YOLO MP):** `"type": "ObjectDetectorYolo"`, `"execution_mode": "process"`.  
**Deprecated:** `"type": "ObjectDetectorYoloMp"` — legacy class; используйте `ObjectDetectorYolo` + `execution_mode`. Проверка: `python scripts/validate_config.py <config.json>`.

При `execution_mode=thread` каждый поток детекции загружает **отдельную** копию весов в RAM/VRAM; при `process` — отдельный дочерний процесс на воркер (`YoloRuntime` только в child). Увеличение `num_detection_threads` умножает потребление памяти.

См. [thread_vs_mp_contracts.md](thread_vs_mp_contracts.md), [MULTIPROCESSING.md](MULTIPROCESSING.md).

**Примеры конфигураций детекторов**:

- **YOLO**: [single_video.json](../evileye/samples_configs/single_video.json)
- **RT-DETR**: [single_video_rtdetr.json](../evileye/samples_configs/single_video_rtdetr.json)
- **RF-DETR**: [single_video_rfdetr.json](../evileye/samples_configs/single_video_rfdetr.json)

#### `trackers`

Массив конфигураций трекеров объектов. Каждый трекер определяет:
- Тип трекера (BoTSORT)
- Источники для трекинга
- Параметры трекинга

**Пример**:
```json
"trackers": [
  {
    "source_ids": [0],
    "fps": 5,
    "botsort_cfg": {
      "tracker_type": "botsort",
      "track_high_thresh": 0.5,
      "track_low_thresh": 0.1,
      "new_track_thresh": 0.6,
      "track_buffer": 30,
      "match_thresh": 0.8,
      "proximity_thresh": 0.5,
      "appearance_thresh": 0.25,
      "gmc_method": "sparseOptFlow",
      "with_reid": true
    }
  }
]
```

**Параметры трекера**:

| Параметр | Тип | Описание | По умолчанию |
|----------|-----|----------|--------------|
| `source_ids` | array | Идентификаторы источников для трекинга | - |
| `fps` | int | FPS для трекинга | `5` |
| `tracker_type` | string | Тип трекера | `botsort` |
| `track_high_thresh` | float | Высокий порог для трекинга | `0.5` |
| `track_low_thresh` | float | Низкий порог для трекинга | `0.1` |
| `new_track_thresh` | float | Порог для создания нового трека | `0.6` |
| `track_buffer` | int | Буфер кадров для трекинга | `30` |
| `match_thresh` | float | Порог совпадения треков | `0.8` |
| `proximity_thresh` | float | Порог близости объектов | `0.5` |
| `appearance_thresh` | float | Порог внешнего вида для re-identification | `0.25` |
| `gmc_method` | string | Метод глобального движения камеры | `sparseOptFlow` |
| `with_reid` | boolean | Использовать re-identification | `false` |
| `execution_mode` | string | `"thread"` / `"process"` (BoT-SORT в child при process, см. contracts §11b) | `"process"` default |

#### `mc_trackers`

Конфигурация межкамерного трекинга для связывания объектов между разными камерами.

**Важно:** `mc_trackers` **не** поддерживает `execution_mode: process` — только синхронный `sync_batch` в parent ([contracts §7](thread_vs_mp_contracts.md)). `validate_config.py` выдаёт предупреждение при попытке указать process.

**Пример**:
```json
"mc_trackers": [
  {
    "enable": true,
    "source_ids": [0, 1]
  }
]
```

**Параметры**:

| Параметр | Тип | Описание | По умолчанию |
|----------|-----|----------|--------------|
| `enable` | boolean | Включить межкамерный трекинг | `false` |
| `source_ids` | array | Идентификаторы источников для межкамерного трекинга | - |

**Примеры**:
- **Включен**: [multi_videos.json](../evileye/samples_configs/multi_videos.json)
- **Отключен**: [single_video.json](../evileye/samples_configs/single_video.json)

### Секция `controller`

Настройки контроллера системы.

**Пример**:
```json
"controller": {
  "fps": 5,
  "enable_close_from_gui": true,
  "class_names": [...],
  "class_mapping": {...},
  "use_database": true,
  "auto_restart": false,
  "scheduled_restart": {
    "enabled": false,
    "mode": "daily_time",
    "time": "01:00",
    "interval_minutes": 0
  }
}
```

**Параметры**:

| Параметр | Тип | Описание | По умолчанию |
|----------|-----|----------|--------------|
| `fps` | int | FPS обработки контроллера | `30` |
| `enable_close_from_gui` | boolean | Разрешить закрытие из GUI | `true` |
| `class_names` | array | Массив имен классов COCO | - |
| `class_mapping` | object | Маппинг имен классов на ID | - |
| `use_database` | boolean | Использовать базу данных | `true` |
| `auto_restart` | boolean | Автоматический перезапуск | `false` |
| `scheduled_restart` | object | Настройки планового перезапуска | - |

**Плановый перезапуск** (`scheduled_restart`):

| Параметр | Тип | Описание | По умолчанию |
|----------|-----|----------|--------------|
| `enabled` | boolean | Включить плановый перезапуск | `false` |
| `mode` | string | Режим: `daily_time` или `interval` | `daily_time` |
| `time` | string | Время перезапуска (формат `HH:MM`) | `01:00` |
| `interval_minutes` | int | Интервал в минутах для режима `interval` | `0` |

Также задайте GUI-флаги в `controller` (не только в `visualizer`): `show_main_gui`, `gui_enabled`, `show_journal`.

### Секция `server`

Встроенный FastAPI web UI / API при `evileye run` (когда `server.enabled: true`).

```json
"server": {
  "enabled": false,
  "execution_mode": "process",
  "host": "127.0.0.1",
  "port": 8181,
  "log_level": "info",
  "preview_encoder": "turbojpeg",
  "preview_encode_workers": 2,
  "ssl_certfile": "certs/server.crt",
  "ssl_keyfile": "certs/server.key",
  "hsts": false,
  "public_base_url": "https://192.168.1.50:8181"
}
```

| Параметр | Описание |
|----------|----------|
| `enabled` | Поднять web-сервер из runtime |
| `host` / `port` | Bind (для LAN часто `0.0.0.0`; TLS слушает тот же порт) |
| `ssl_certfile` / `ssl_keyfile` | PEM-пара. Пустые/отсутствующие = HTTP. IP и DNS должны быть в SAN сертификата (не только CN) |
| `hsts` | Opt-in Strict-Transport-Security. Default `false`. Не путать с `secure_cookies` |
| `public_base_url` | Публичный URL UI (читается также из credentials, если там задан) |
| `preview_encoder` | `turbojpeg` (предпочтительно) или fallback OpenCV |
| `preview_encode_workers` | Число encode-workers для live preview |

Для реального TurboJPEG нужны пакет `PyTurboJPEG` и системная `libturbojpeg` (`sudo apt install libturbojpeg`). Без библиотеки система стартует с OpenCV fallback. См. [`CLI_SETUP_WEB.md`](CLI_SETUP_WEB.md), `evileye setup-web`.

### Секция `record`

Непрерывная и/или event-запись. Top-level значения могут переопределяться per-source вложенным `"record": {...}`.

```json
"record": {
  "enabled": false,
  "continuous_recording_enabled": false,
  "event_recording_enabled": false,
  "event_pre_seconds": 5,
  "event_post_seconds": 5,
  "segment_length_sec": 1800,
  "retention_days": 7,
  "container": "mp4",
  "filename_tmpl": "{source_name}_{start_time}_{seq}.{ext}"
}
```

Файлы continuous-записи попадают в `EvilEyeData/Streams/YYYY-MM-DD/...` (или `out_dir` / `database.image_dir`) и используются web playback.

Samples поставляются с `enabled: false`. Для production-like записи см. [`poly-cameras-gst.json`](../configs/poly-cameras-gst.json).

### Секция `objects_handler`

Настройки управления объектами.

**Пример**:
```json
"objects_handler": {
  "max_active_objects": 100,
  "max_lost_objects": 100,
  "lost_thresh": 5,
  "lost_store_time_secs": 60,
  "history_len": 30,
  "attributes_detection": {
    "primary_by_name": ["person"],
    "primary_by_id": [0],
    "secondary_by_name": ["hard_hat", "no_hard_hat"],
    "secondary_by_id": [0, 1],
    "confidence_thresholds": {
      "hard_hat": 0.5,
      "no_hard_hat": 0.5
    },
    "time_thresholds": {
      "min_time_ms": 600,
      "confirm_time_ms": 2000
    },
    "ema_alpha": 0.7
  }
}
```

**Параметры**:

| Параметр | Тип | Описание | По умолчанию |
|----------|-----|----------|--------------|
| `max_active_objects` | int | Максимальное количество активных объектов | `100` |
| `max_lost_objects` | int | Максимальное количество потерянных объектов | `100` |
| `lost_thresh` | int | Порог кадров для перехода в lost | `5` |
| `lost_store_time_secs` | int | Время хранения потерянных объектов (секунды) | `60` |
| `history_len` | int | Длина истории объектов | `30` |
| `attributes_detection` | object | Настройки детекции атрибутов | - |

**Детекция атрибутов** (`attributes_detection`):

| Параметр | Тип | Описание |
|----------|-----|----------|
| `primary_by_name` | array | Имена основных классов для атрибутов |
| `primary_by_id` | array | ID основных классов |
| `secondary_by_name` | array | Имена вторичных классов (атрибутов) |
| `secondary_by_id` | array | ID вторичных классов |
| `confidence_thresholds` | object | Пороги уверенности для каждого атрибута |
| `time_thresholds` | object | Пороги времени для состояний атрибутов |
| `ema_alpha` | float | Коэффициент EMA-сглаживания |

**Пример с атрибутами**: [single_video_with_attributes.json](../evileye/samples_configs/single_video_with_attributes.json)

### Секция `events_detectors`

Настройки детекторов событий.

**Пример**:
```json
"events_detectors": {
  "CamEventsDetector": {},
  "FieldOfViewEventsDetector": {
    "sources": {}
  },
  "ZoneEventsDetector": {
    "sources": {},
    "event_threshold": 0,
    "zone_left_threshold": 0
  },
  "AttributeEventsDetector": {
    "sources": {}
  },
  "SystemEventsDetector": {}
}
```

**Типы детекторов событий**:

- **CamEventsDetector** - События камер (старт, стоп, ошибки)
- **FieldOfViewEventsDetector** - События появления объектов в поле зрения
- **ZoneEventsDetector** - События входа/выхода объектов из зон
- **AttributeEventsDetector** - События изменения атрибутов объектов
- **SystemEventsDetector** - Системные события

Подробнее о детекторах событий см. [ARCHITECTURE.md](ARCHITECTURE.md#уровень-6-обработка-событий).

### Секция `database`

Настройки базы данных PostgreSQL.

**Пример**:
```json
"database": {
  "database_name": "evil_eye_db",
  "host_name": "localhost",
  "port": 5432,
  "admin_user_name": "postgres",
  "admin_password": "",
  "image_dir": "EvilEyeData",
  "preview_width": 300,
  "preview_height": 150
}
```

**Параметры**:

| Параметр | Тип | Описание | По умолчанию |
|----------|-----|----------|--------------|
| `database_name` | string | Имя базы данных | `evil_eye_db` |
| `host_name` | string | Хост базы данных | `localhost` |
| `port` | int | Порт базы данных | `5432` |
| `admin_user_name` | string | Имя пользователя администратора | `postgres` |
| `admin_password` | string | Пароль администратора | - |
| `image_dir` | string | Директория для сохранения изображений | `EvilEyeData` |
| `preview_width` | int | Ширина превью изображений | `300` |
| `preview_height` | int | Высота превью изображений | `150` |

**Примечание**: Если секция `database` отсутствует или параметры некорректны, система автоматически переключится на JSON режим хранения данных.

### Секция `database_adapters`

Настройки адаптеров базы данных для различных типов данных (объекты, события). Адаптеры управляются централизованно через `DatabaseService` и запускаются/останавливаются единообразно.

**Пример**:
```json
"database_adapters": {
  "DatabaseAdapterObjects": {
    "batch_size": 10,
    "batch_timeout": 0.1
  },
  "DatabaseAdapterCamEvents": {
    "batch_size": 10,
    "batch_timeout": 0.1
  },
  "DatabaseAdapterFieldOfViewEvents": {
    "batch_size": 10,
    "batch_timeout": 0.1
  },
  "DatabaseAdapterZoneEvents": {
    "batch_size": 10,
    "batch_timeout": 0.1
  },
  "DatabaseAdapterAttributeEvents": {
    "batch_size": 10,
    "batch_timeout": 0.1
  },
  "DatabaseAdapterSystemEvents": {
    "batch_size": 10,
    "batch_timeout": 0.1
  }
}
```

**Параметры адаптеров**:

| Параметр | Тип | Описание | По умолчанию |
|----------|-----|----------|--------------|
| `batch_size` | int | Размер батча для группировки запросов к БД | `10` |
| `batch_timeout` | float | Максимальное время ожидания для формирования батча (секунды) | `0.1` |

**Примечания**:
- Батчинг позволяет группировать несколько запросов в один для повышения производительности
- `batch_size=1` означает обработку запросов по одному (батчинг отключен)
- `batch_timeout` определяет максимальное время ожидания перед отправкой неполного батча
- Адаптеры автоматически создаются и управляются через `DatabaseService` при инициализации БД
- При ошибках запуска адаптеров (например, `threads can only be started once`) подключение к БД может остаться активным, но адаптеры будут отключены

Подробнее о настройке базы данных см. [DATABASE_SETUP_GUIDE.md](DATABASE_SETUP_GUIDE.md).

### Секция `visualizer`

Настройки визуализации и GUI.

**Пример**:
```json
"visualizer": {
  "num_width": 1,
  "num_height": 1,
  "visual_buffer_num_frames": 10,
  "source_ids": [0],
  "fps": [5],
  "gui_enabled": true,
  "show_debug_info": true,
  "objects_journal_enabled": true,
  "text_config": {
    "font_size_pt": 42,
    "font_face": 0,
    "color": [0, 0, 255],
    "thickness": null,
    "background_color": [0, 0, 0],
    "background_enabled": false,
    "padding_percent": 1.5,
    "position_offset_percent": [0, -8],
    "font_scale_method": "resolution_based",
    "base_resolution": [1920, 1080]
  }
}
```

**Параметры**:

| Параметр | Тип | Описание | По умолчанию |
|----------|-----|----------|--------------|
| `num_width` | int | Количество колонок в сетке отображения | `1` |
| `num_height` | int | Количество строк в сетке отображения | `1` |
| `visual_buffer_num_frames` | int | Размер буфера кадров для визуализации | `10` |
| `source_ids` | array | Идентификаторы источников для отображения | - |
| `fps` | array | FPS для каждого источника | - |
| `gui_enabled` | boolean | Включить GUI | `true` |
| `show_debug_info` | boolean | Показывать отладочную информацию | `true` |
| `objects_journal_enabled` | boolean | Включить журнал объектов | `true` |
| `text_config` | object | Настройки отрисовки текста | - |

**Настройки текста** (`text_config`):

| Параметр | Тип | Описание | По умолчанию |
|----------|-----|----------|--------------|
| `font_size_pt` | int | Размер шрифта в пунктах | `12` |
| `font_face` | int | Тип шрифта OpenCV | `0` |
| `color` | array | Цвет текста (BGR) | `[255, 255, 255]` |
| `thickness` | int/null | Толщина шрифта (авто если null) | `null` |
| `background_color` | array/null | Цвет фона (BGR) | `null` |
| `background_enabled` | boolean | Включить фон | `false` |
| `padding_percent` | float | Отступ вокруг текста (проценты) | `2.0` |
| `position_offset_percent` | array | Смещение от bbox (проценты) | `[0, -10]` |
| `font_scale_method` | string | Метод масштабирования | `resolution_based` |
| `base_resolution` | array | Базовое разрешение для масштабирования | `[1920, 1080]` |

Подробнее о системе рендеринга текста см. [TEXT_RENDERING_SYSTEM.md](TEXT_RENDERING_SYSTEM.md).

### Секция `storage_monitor`

Настройки мониторинга хранилища.

**Пример**:
```json
"storage_monitor": {
  "enabled": true,
  "check_interval_seconds": 300,
  "max_dir_size_gb": 200,
  "min_free_space_percent": 10,
  "retention_days": {
    "streaming_video": 7,
    "event_videos": 7,
    "object_images": 180,
    "event_images": 180
  },
  "active_file_age_seconds": 60
}
```

**Параметры**:

| Параметр | Тип | Описание | По умолчанию |
|----------|-----|----------|--------------|
| `enabled` | boolean | Включить мониторинг хранилища | `true` |
| `check_interval_seconds` | int | Интервал проверки (секунды) | `300` |
| `max_dir_size_gb` | int | Максимальный размер директории (GB) | `200` |
| `min_free_space_percent` | int | Минимальный свободный объем (проценты) | `10` |
| `retention_days` | object | Дни хранения для разных типов файлов | - |
| `active_file_age_seconds` | int | Возраст активного файла (секунды) | `60` |

**Дни хранения** (`retention_days`):

| Параметр | Тип | Описание | По умолчанию |
|----------|-----|----------|--------------|
| `streaming_video` | int | Дни хранения видео потоков | `7` |
| `event_videos` | int | Дни хранения видео событий | `7` |
| `object_images` | int | Дни хранения изображений объектов | `180` |
| `event_images` | int | Дни хранения изображений событий | `180` |

## Валидация конфигураций

Система EvilEye включает встроенный валидатор конфигураций (`ConfigValidator`), который проверяет корректность конфигурационных файлов перед запуском системы.

### Использование валидации

Для проверки корректности конфигурационного файла используйте:

```bash
evileye validate configs/my_config.json
```

**Фактически в коде:**

- **Hard-fail (CLI `validate_config`)**: обязательны секция `pipeline`, непустой `pipeline.sources`, у каждого источника поля `source` и `camera`.
- **Soft (Pydantic `ConfigValidator`)**: при наличии секций проверяются типы/`fps`/`port` и т.п.; неизвестные ключи игнорируются. При `evileye run` ошибка pydantic обычно даёт **warning**, запуск продолжается.
- Секции `server` / `record` / `scheduled_restart` **не** являются hard-required, но рекомендуются в актуальных шаблонах.

Команда также проверяет корректность JSON-синтаксиса.

### Автоматическая валидация

Валидация также выполняется автоматически:
- **При запуске через CLI**: команда `evileye run` автоматически валидирует конфигурацию перед запуском
- **При загрузке конфигурации**: `run_config_helper` валидирует конфигурацию при загрузке
- **В GUI**: при сохранении конфигурации через Configurer выполняется базовая валидация

### Типы проверок

`ConfigValidator` (soft) выполняет следующие проверки:

1. **Валидация секции `pipeline`** (если есть): `pipeline_class`, структура `sources` / `detectors` / `trackers` через Pydantic-модели.
2. **Валидация секции `database`** (если есть): поля вроде `database_name`, `host_name`, `port` (1–65535).
3. **Валидация секции `controller`** (если есть): диапазон FPS (1–120), булевы флаги. Поле `scheduled_restart` поддерживается runtime/CLI scheduler; pydantic-модель может его не описывать — отсутствие в soft-модели не блокирует запуск.

Регрессионный lint актуальности шаблонов: `tests/unit/config/test_config_actuality_lint.py` (наличие `server`/`record`/GST-флагов в samples и канонических configs).

### Обработка ошибок

При обнаружении ошибок валидации:
- **Hard CLI**: отсутствует `pipeline` / `sources` / `source`+`camera` → отказ запуска
- **Soft pydantic**: сообщение/warning по секции; запуск часто продолжается
- **В GUI**: ошибки отображаются пользователю с возможностью исправления

### Примеры ошибок валидации

```bash
# Ошибка: отсутствует обязательная секция pipeline / sources
$ evileye validate invalid.json
Error: ... missing pipeline / sources ...

# Soft: некорректный тип в database (часто warning при run)
$ evileye validate invalid.json
... Database config error: Input should be a valid integer ...
```

### Расширенная валидация

При наличии библиотеки `pydantic` система использует расширенную валидацию с проверкой типов и диапазонов значений. Если `pydantic` недоступен, выполняется базовая проверка структуры конфигурации.

Дополнительно для MP-рефакторинга: `python scripts/validate_config.py <path.json>` — legacy `ObjectDetectorYoloMp`, `mc_trackers` + process (см. [developing_dual_mode_modules.md](developing_dual_mode_modules.md)).

### Зарегистрированные `type` (`@EvilEyeBase.register`)

| type | Назначение |
|------|------------|
| ObjectDetectorYolo | YOLO детектор (primary) |
| ObjectDetectorRtdetr | RT-DETR |
| ObjectDetectorRfdetr | RF-DETR |
| ObjectDetectorYoloMp | Legacy (deprecated) |
| ObjectTrackingBotsort | Per-source tracker |
| ObjectMultiCameraTracking | MC tracker (sync only) |
| VideoCaptureGStreamer / VideoCaptureOpencv | Capture backends |
| AttributeClassifier / AttributeDetector / RoiFeeder | Attributes pipeline |
| PreprocessingPipeline | Preprocessing stage |

Полный индекс кода: [CODE_MODULE_INDEX.md](CODE_MODULE_INDEX.md).

## Связанные документы

- [Pipeline Architecture](PIPELINE_ARCHITECTURE.md) - Архитектура pipeline классов
- [Database Setup Guide](DATABASE_SETUP_GUIDE.md) - Настройка базы данных
- [Attributes Detection](ATTRIBUTES_DETECTION_README.md) - Детекция атрибутов объектов
- [Text Rendering System](TEXT_RENDERING_SYSTEM.md) - Система рендеринга текста
- [GStreamer Usage](VideoCaptureGStreamer_Usage.md) - Использование GStreamer
- [System Architecture](ARCHITECTURE.md) - Полная архитектура системы
- [Thread vs MP contracts](thread_vs_mp_contracts.md) - `execution_mode`, MP modules
- [MULTIPROCESSING.md](MULTIPROCESSING.md) - env и ops
