# EvilEye Configuration Creator

## Обзор

Команда `evileye create` предназначена для создания новых конфигурационных файлов для системы EvilEye. Использует контроллер для генерации базовой конфигурации и добавляет источники согласно указанным параметрам.

## Использование

### Базовое использование

```bash
# Создать базовую конфигурацию
evileye create my_config

# Создать конфигурацию с указанным количеством источников
evileye create my_config --sources 2

# Создать конфигурацию с определенным типом pipeline
evileye create my_config --pipeline PipelineSurveillance

# Создать конфигурацию с определенным типом источников
evileye create my_config --source-type video_file
```

### Типы источников

**Доступные типы источников:**
- `video_file` - Видеофайлы (по умолчанию)
- `ip_camera` - IP-камеры
- `device` - Устройства (веб-камеры)

### Параметры командной строки

```bash
evileye create [config_name] [options]

positional arguments:
  config_name           Имя конфигурационного файла (без расширения .json)

options:
  -h, --help            Показать справку
  --sources SOURCES     Количество видео источников (по умолчанию: 0)
  --pipeline PIPELINE   Имя класса pipeline (по умолчанию: PipelineSurveillance)
  --source-type {video_file,ip_camera,device}
                       Тип источников (по умолчанию: video_file)
  --output-dir OUTPUT_DIR
                       Директория для сохранения файлов (по умолчанию: configs)
  --force               Перезаписать существующий файл
  --list-pipelines      Показать список доступных pipeline классов
  --detector-model PATH Путь к модели детектора
  --tracker-type TYPE   Тип трекера
  --db/--no-db          Включить/отключить базу данных
```

## Примеры

### Создание базовой конфигурации
```bash
evileye create basic_config
# Создает: configs/basic_config.json
```

### Создание конфигурации с видеофайлами
```bash
evileye create video_config --sources 2 --source-type video_file
# Создает: configs/video_config.json с 2 видеофайлами
```

### Создание конфигурации с IP-камерами
```bash
evileye create ip_cameras --sources 3 --source-type ip_camera
# Создает: configs/ip_cameras.json с 3 IP-камерами
```

### Создание конфигурации с устройствами
```bash
evileye create devices --sources 2 --source-type device
# Создает: configs/devices.json с 2 устройствами
```

### Создание конфигурации с определенным pipeline
```bash
# Список доступных pipeline классов
evileye create --list-pipelines

# Создание с конкретным pipeline
evileye create custom_config --sources 2 --pipeline PipelineSurveillance
# Создает: configs/custom_config.json с указанным pipeline

# Создание с PipelineCapture (простая capture pipeline)
evileye create capture_config --pipeline PipelineCapture --sources 1
# Создает: configs/capture_config.json с PipelineCapture
```

## Структура создаваемых файлов

### Конфигурация источников
В зависимости от типа источника создаются соответствующие настройки:

**Video File:**
```json
{
    "camera": "video_1.mp4",
    "source": "VIDEO_FILE",
    "source_ids": [0],
    "source_names": ["Source 1"],
    "loop_play": true,
    "desired_fps": 30
}
```

**IP Camera:**
```json
{
    "camera": "rtsp://camera_1/stream",
    "source": "IP_CAMERA",
    "source_ids": [0],
    "source_names": ["Source 1"],
    "loop_play": true,
    "desired_fps": 30,
    "username": "admin",
    "password": "password"
}
```

**Device:**
```json
{
    "camera": "0",
    "source": "DEVICE",
    "source_ids": [0],
    "source_names": ["Source 1"],
    "loop_play": true,
    "desired_fps": 30
}
```

## Pipeline Classes

### Автоматическое обнаружение
Скрипт автоматически обнаруживает доступные pipeline классы в:
- `evileye.pipelines` пакете
- Локальной папке `pipelines/` в текущей директории

### Доступные Pipeline классы
- **PipelineSurveillance** - Полный pipeline с детекцией, трекингом и мультикамерой
- **PipelineCapture** - Простая pipeline для захвата видео из одного файла

### Создание собственных Pipeline классов
1. Создайте папку `pipelines/` в вашей рабочей директории
2. Создайте файл `pipelines/my_pipeline.py`:
   ```python
   from evileye.core.pipeline_processors import PipelineProcessors
   
   class MyPipeline(PipelineProcessors):
       def init_impl(self, **kwargs):
           # Ваша логика инициализации
           return True
   ```
3. Создайте `pipelines/__init__.py`:
   ```python
   from .my_pipeline import MyPipeline
   __all__ = ['MyPipeline']
   ```
4. Используйте: `evileye create --pipeline MyPipeline`

## Интеграция

Команда интегрирована в систему EvilEye:

1. **CLI команда:** `evileye create`
2. **Основной модуль:** `evileye/cli.py` (функция `create`)

## Использование в других скриптах

```python
from evileye.create import create_config_file

# Создать конфигурацию программно
success = create_config_file(
    config_name="my_config",
    sources=2,
    pipeline_class="PipelineSurveillance",
    source_type="video_file",
    output_dir="configs",
    force=False
)
```
