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
  "objects_handler": {...},
  "events_detectors": {...},
  "database": {...},
  "visualizer": {...},
  "storage_monitor": {...}
}
```

**Важно**: Структура конфигурации зависит от выбранного класса pipeline. Данное руководство описывает конфигурацию для `PipelineSurveillance`. Для других классов pipeline (например, `PipelineCapture`) структура может отличаться.

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
| `username` | string | Имя пользователя для IP камеры | Нет |
| `password` | string | Пароль для IP камеры | Нет |

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
| `type` | string | Тип детектора: `ObjectDetectorRtdetr`, `ObjectDetectorRfdetr` (для YOLO не требуется) | - |
| `model` | string | Путь к модели детектора | `models/yolo11n.pt` |
| `source_ids` | array | Идентификаторы источников для обработки | - |
| `classes` | array | Классы объектов COCO для детекции | `[0, 1, 24, 25, 63, 66, 67]` |
| `inference_size` | int | Размер входного изображения для модели | `640` |
| `conf` | float | Порог уверенности детекции | `0.25` |
| `roi` | array | Области интереса (Regions of Interest) | `[[]]` |
| `vid_stride` | int | Шаг обработки кадров | `1` |
| `num_detection_threads` | int | Количество потоков для детекции | `1` |

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

#### `mc_trackers`

Конфигурация межкамерного трекинга для связывания объектов между разными камерами.

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

Команда проверит:
- Корректность JSON синтаксиса
- Наличие обязательных секций (`pipeline`, `database`, `controller`)
- Корректность типов параметров (используя Pydantic модели, если доступен)
- Существование указанных файлов и путей

### Автоматическая валидация

Валидация также выполняется автоматически:
- **При запуске через CLI**: команда `evileye run` автоматически валидирует конфигурацию перед запуском
- **При загрузке конфигурации**: `run_config_helper` валидирует конфигурацию при загрузке
- **В GUI**: при сохранении конфигурации через Configurer выполняется базовая валидация

### Типы проверок

`ConfigValidator` выполняет следующие проверки:

1. **Валидация секции `pipeline`**:
   - Проверка наличия `pipeline_class`
   - Проверка структуры `sources`, `detectors`, `trackers`
   - Валидация типов данных через Pydantic модели (если доступен)

2. **Валидация секции `database`**:
   - Проверка обязательных полей (`database_name`, `host_name`, `port`)
   - Валидация диапазона порта (1-65535)
   - Проверка корректности типов данных

3. **Валидация секции `controller`**:
   - Проверка диапазона FPS (1-120)
   - Валидация булевых флагов
   - Проверка структуры `scheduled_restart`

### Обработка ошибок

При обнаружении ошибок валидации:
- **В CLI**: выводится сообщение об ошибке с указанием проблемной секции и деталями
- **При запуске**: система может отказаться от запуска или переключиться в fallback режим (например, JSON вместо БД)
- **В GUI**: ошибки отображаются пользователю с возможностью исправления

### Примеры ошибок валидации

```bash
# Ошибка: отсутствует обязательная секция
$ evileye validate invalid.json
Error: Pipeline config error: Field required [type=missing, input={}, input_type=dict]

# Ошибка: некорректный тип данных
$ evileye validate invalid.json
Error: Database config error: Input should be a valid integer [type=int_parsing, input='invalid', input_type=str]
```

### Расширенная валидация

При наличии библиотеки `pydantic` система использует расширенную валидацию с проверкой типов и диапазонов значений. Если `pydantic` недоступен, выполняется базовая проверка структуры конфигурации.

## Связанные документы

- [Pipeline Architecture](PIPELINE_ARCHITECTURE.md) - Архитектура pipeline классов
- [Database Setup Guide](DATABASE_SETUP_GUIDE.md) - Настройка базы данных
- [Attributes Detection](ATTRIBUTES_DETECTION_README.md) - Детекция атрибутов объектов
- [Text Rendering System](TEXT_RENDERING_SYSTEM.md) - Система рендеринга текста
- [GStreamer Usage](VideoCaptureGStreamer_Usage.md) - Использование GStreamer
- [System Architecture](ARCHITECTURE.md) - Полная архитектура системы
