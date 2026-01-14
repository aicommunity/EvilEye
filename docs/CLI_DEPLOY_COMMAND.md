# Команда `evileye deploy`

## Обзор

Команда `evileye deploy` предназначена для быстрого развертывания базовых конфигурационных файлов EvilEye в текущей директории.

## Функциональность

Команда выполняет следующие действия:

1. **Копирует `credentials_proto.json` в `credentials.json`** (только если `credentials.json` не существует)
2. **Создает папку `configs`** (только если она не существует)

## Использование

### Базовое использование
```bash
evileye deploy
```

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
✓ Copied credentials_proto.json to credentials.json
✓ Created configs folder
✓ Deployment completed successfully!
You can now create configurations with:
  evileye create my_config --sources 1
```

### Повторный запуск (файлы уже существуют)
```
Deploying EvilEye files to: /path/to/current/directory
credentials.json already exists, skipping...
configs folder already exists, skipping...
✓ Deployment completed successfully!
You can now create configurations with:
  evileye create my_config --sources 1
```

## Создаваемые файлы

### `credentials.json`
Скопированный из `evileye/credentials_proto.json` файл с шаблоном учетных данных:

```json
{
  "sources" : {
    "rtsp://name": {
      "username": "user",
      "password": "password"
    }
  },
  "database": {
    "user_name": "postgres",
    "password": "",
    "database_name": "evil_eye_db",
    "host_name": "localhost",
    "port": 5432,
    "default_database_name": "postgres",
    "default_password": "",
    "default_user_name": "postgres",
    "default_host_name": "localhost",
    "default_port": 5432
  }
}
```

### `configs/`
Пустая директория для хранения конфигурационных файлов.

## Рабочий процесс

1. **Развертывание:**
   ```bash
   evileye deploy
   ```

2. **Создание конфигурации:**
   ```bash
   evileye create my_config --sources 2 --source-type video_file
   ```

3. **Запуск системы:**
   ```bash
   evileye run configs/my_config.json
   ```

## Безопасность

- Команда **не перезаписывает** существующие файлы
- `credentials.json` создается только если не существует
- Папка `configs` создается только если не существует
- Все операции безопасны и не повреждают существующие данные

## Интеграция с другими командами

Команда `deploy` является первым шагом в рабочем процессе:

1. `evileye deploy` - развертывание базовых файлов
2. `evileye create` - создание конфигураций
3. `evileye run` - запуск системы
4. `evileye validate` - проверка конфигураций

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


