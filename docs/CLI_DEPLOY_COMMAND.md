# Команда `evileye deploy`

## Обзор

Команда `evileye deploy` предназначена для быстрого развертывания базовых конфигурационных файлов EvilEye в текущей директории.

## Функциональность

Команда выполняет следующие действия:

1. **Копирует `credentials_proto.json` в `credentials.json`** (только если `credentials.json` не существует)
2. **Создает папку `configs`** (только если она не существует)
3. **Разворачивает `monitor/`** — скрипты watchdog и шаблоны systemd (без запуска сервисов)
4. **Создает `logs/`**, а также `monitor/incidents/` и `monitor/reports/`

Команда **не** включает systemd timers watchdog и **не** запускает pipeline runtime.
В конце `deploy` вызывает **ensure** `evileye service-install` (Web UI OS-сервис).
Ошибка установки сервиса не отменяет deploy — сайт всё равно создаётся.

Для активации watchdog отдельно:

```bash
DEPLOY_DIR=$PWD ./monitor/scripts/install_timer.sh
```

См. также [`CLI_SERVICE_COMMANDS.md`](CLI_SERVICE_COMMANDS.md) (`service-install` / `service-uninstall`).

## Использование

### Базовое использование
```bash
evileye deploy
```

Важно: запускайте `deploy`, `server` и `run` из одной и той же site-директории.
Текущая рабочая директория становится корнем сайта для `credentials.json`,
`configs/`, `logs/`, `monitor/` и связанных runtime-файлов.

### Справка
```bash
evileye deploy --help
```

## Примеры

### Развертывание в новой директории
```bash
# Создаем новую директорию
mkdir my_evileye_project
cd my_evileye_project

# Развертываем файлы
evileye deploy
```

### Результат выполнения
```
Deploying EvilEye files to: /path/to/current/directory
Copied credentials_proto.json to credentials.json
Created configs folder
Deployed monitor assets (... scripts, ... systemd templates) → .../monitor
Note: watchdog timers were not enabled; run install_timer.sh when ready
Deployment completed successfully!
```

### Повторный запуск (файлы уже существуют)
```
Deploying EvilEye files to: /path/to/current/directory
credentials.json already exists, skipping...
configs folder already exists, skipping...
Deployed monitor assets (... ) → .../monitor   # scripts/systemd обновляются
Deployment completed successfully!
```

## Создаваемые файлы

### `credentials.json`
Скопированный из `evileye/credentials_proto.json` файл с шаблоном учетных данных.
`deploy` не создаёт bootstrap admin в открытом виде: первый web admin генерируется
при первом старте сервера, пароль печатается в лог, после входа требуется его смена.

```json
{
  "sources" : {
    "rtsp://name": {
      "username": "user",
      "password": ""
    }
  },
  "database": {
    "user_name": "postgres",
    "password": "",
    "database_name": "evil_eye_db",
    "host_name": "localhost",
    "port": 5432,
    "admin_user_name": "postgres",
    "admin_password": ""
  },
  "web_auth": {
    "enabled": true,
    "session_secret": "",
    "secure_cookies": false,
    "internal_token": "",
    "protection": {
      "enabled": true,
      "trust_proxy": false,
      "trusted_proxy_ips": ["127.0.0.1"],
      "whitelist_ips": ["127.0.0.1", "::1"]
    },
    "users": []
  }
}
```

См. также шаблон [`evileye/credentials_proto.json`](../evileye/credentials_proto.json) и [`docs/CONFIGURATION_GUIDE.md`](CONFIGURATION_GUIDE.md).

### `configs/`
Пустая директория для хранения конфигурационных файлов.

### `logs/`
Директория для логов сессий `*_evileye_main.log`.

### `monitor/`
Скрипты и шаблоны для бесперебойной работы (watchdog):

- `scripts/` — `health_check.sh`, `restart_evileye.sh`, `install_timer.sh`, …
- `systemd/` — шаблоны user units (`KillMode=process`)
- `incidents/`, `reports/` — runtime-каталоги (пустые при deploy)
- `INSTALL_HINT.txt` — как включить timer вручную

Исходники в репозитории: [`deploy/monitor/`](../deploy/monitor/), в пакете: `evileye/deploy_monitor/`.

## Рабочий процесс

1. **Развертывание:**
   ```bash
   evileye deploy
   ```

2. **Поднять Web UI / backend:**
   ```bash
   evileye server --host 0.0.0.0 --port 8181 --no-reload
   ```

3. **Первый вход и Basic Setup:**
   - открыть `http://<host>:8181`
   - войти как `admin` с bootstrap-паролем из лога первого старта
   - сменить пароль
   - в разделе **Настройка** сохранить Basic Setup в `configs/system.json`

4. **(Опционально) включить watchdog:**
   ```bash
   DEPLOY_DIR=$PWD ./monitor/scripts/install_timer.sh
   ```

5. **Запуск runtime (после настройки):**
   ```bash
   evileye run configs/system.json --no-gui
   ```

`evileye deploy` подготавливает **site directory** для Web UI. Команда `evileye create`
остаётся полезной для ручного config-first workflow, но больше не является обязательным
первым шагом на новой машине.

## Безопасность

- Команда **не перезаписывает** существующие файлы
- `credentials.json` создается только если не существует
- Папка `configs` создается только если не существует
- Все операции безопасны и не повреждают существующие данные

## Интеграция с другими командами

Команда `deploy` является первым шагом в web-first рабочем процессе:

1. `evileye deploy` - развертывание базовых файлов
2. `evileye server` / OS service - запуск Web UI/backend
3. Basic Setup в браузере - создание и сохранение `configs/system.json`
4. `evileye run configs/system.json --no-gui` - запуск runtime
5. `evileye validate` - проверка конфигураций при ручном редактировании

## Обработка ошибок

- Если `credentials_proto.json` не найден в пакете - ошибка
- Если не удается создать папку `configs` - ошибка
- Если не удается скопировать файл - ошибка
- Все ошибки сопровождаются понятными сообщениями

## Команда `evileye create`

### Обзор

Команда `evileye create` предназначена для создания новых конфигурационных файлов EvilEye с настраиваемыми параметрами.

### Функциональность

Команда позволяет:
- Создавать конфигурации с указанным количеством источников
- Выбирать тип pipeline
- Настраивать типы источников (video_file, ip_camera, device)
- Настраивать параметры детекторов и трекеров
- Управлять настройками базы данных

### Использование

#### Базовое создание конфигурации
```bash
evileye create my_config --sources 2
```

#### Создание конфигурации для IP камер
```bash
evileye create ip_config --sources 1 --source-type ip_camera
```

#### Создание конфигурации с конкретным pipeline
```bash
evileye create test_config --pipeline PipelineSurveillance --sources 3
```

#### Список доступных pipeline классов
```bash
evileye create --list-pipelines
```

#### Создание с дополнительными параметрами
```bash
evileye create advanced_config --sources 2 --detector-model /path/to/model.pt --tracker-type BoTSORT --db
```

### Параметры

- `config_name` - Имя конфигурационного файла (обязательный)
- `--sources` - Количество источников (по умолчанию: 0)
- `--pipeline` - Класс pipeline (по умолчанию: PipelineSurveillance)
- `--source-type` - Тип источников: video_file, ip_camera, device (по умолчанию: video_file)
- `--output-dir` - Директория для сохранения (по умолчанию: configs)
- `--force` - Перезаписать существующий файл
- `--list-pipelines` - Показать список доступных pipeline классов
- `--detector-model` - Путь к модели детектора
- `--tracker-type` - Тип трекера
- `--db/--no-db` - Включить/отключить базу данных

## Связанные команды

Перед первым запуском Web UI на сайте:

```bash
evileye setup-web
```

Подробности: [`CLI_SETUP_WEB.md`](CLI_SETUP_WEB.md).


