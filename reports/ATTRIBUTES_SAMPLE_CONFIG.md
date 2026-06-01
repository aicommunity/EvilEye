# Sample Configuration: Single Video with Attributes

Образец конфигурации для демонстрации системы атрибутов на основе `single_video.json` с поддержкой детекции PPE (Personal Protective Equipment) у людей.

## Файл: `configs/single_video_with_attributes.json`

### Ключевые особенности

1. **Первичный класс**: `person` (class_id: 0)
2. **Атрибуты**: `hard_hat`, `backpack`, `safety_vest`
3. **ROI обработка**: каждые 2 кадра с размером 224x224
4. **Пороги времени**: разные для каждого атрибута

### Структура конфигурации

#### Pipeline секция

```json
{
  "pipeline": {
    "pipeline_class": "PipelineSurveillance",
    "sources": [...],
    "detectors": [...],
    "trackers": [...],
    "attributes_roi": [
      {
        "source_ids": [0],
        "padding": 0.15,
        "size": [224, 224],
        "every_n_frames": 2
      }
    ],
    "attributes_classifier": [
      {
        "source_ids": [0],
        "enabled": true,
        "model": "models/ppe_classifier.onnx",
        "attrs": ["hard_hat", "backpack", "safety_vest"],
        "confidence_thresholds": {
          "hard_hat": 0.6,
          "backpack": 0.5,
          "safety_vest": 0.5
        },
        "time_thresholds": {
          "hard_hat": {
            "min_time_ms": 800,
            "confirm_time_ms": 2000
          },
          "backpack": {
            "min_time_ms": 1000,
            "confirm_time_ms": 2500
          },
          "safety_vest": {
            "min_time_ms": 1200,
            "confirm_time_ms": 3000
          }
        },
        "ema_alpha": 0.7
      }
    ]
  }
}
```

#### Objects Handler секция

```json
{
  "objects_handler": {
    "max_active_objects": 100,
    "max_lost_objects": 100,
    "lost_thresh": 5,
    "lost_store_time_secs": 60,
    "history_len": 1,
    "attributes_detection": {
      "primary_by_name": ["person"],
      "primary_by_id": [0],
      "secondary_by_name": ["hard_hat", "backpack", "safety_vest"],
      "secondary_by_id": [27, 28, 29],
      "roi": {
        "padding": 0.15,
        "size": [224, 224],
        "every_n_frames": 2
      },
      "classifier": {
        "enabled": true,
        "model": "models/ppe_classifier.onnx",
        "attrs": ["hard_hat", "backpack", "safety_vest"],
        "confidence_thresholds": {
          "hard_hat": 0.6,
          "backpack": 0.5,
          "safety_vest": 0.5
        },
        "time_thresholds": {
          "hard_hat": {
            "min_time_ms": 800,
            "confirm_time_ms": 2000
          },
          "backpack": {
            "min_time_ms": 1000,
            "confirm_time_ms": 2500
          },
          "safety_vest": {
            "min_time_ms": 1200,
            "confirm_time_ms": 3000
          }
        },
        "ema_alpha": 0.7
      }
    }
  }
}
```

## Параметры атрибутов

### ROI настройки

- **padding**: 0.15 (15% отступ от bbox)
- **size**: [224, 224] (размер кропа для классификатора)
- **every_n_frames**: 2 (обработка каждого 2-го кадра)

### Пороги доверия

- **hard_hat**: 0.6 (каска требует высокой уверенности)
- **backpack**: 0.5 (рюкзак - средняя уверенность)
- **safety_vest**: 0.5 (жилет - средняя уверенность)

### Временные пороги

| Атрибут | min_time_ms | confirm_time_ms | Описание |
|---------|-------------|-----------------|----------|
| hard_hat | 800 | 2000 | Каска: быстрая потеря, среднее подтверждение |
| backpack | 1000 | 2500 | Рюкзак: медленная потеря, долгое подтверждение |
| safety_vest | 1200 | 3000 | Жилет: самая медленная потеря, долгое подтверждение |

### EMA сглаживание

- **alpha**: 0.7 (70% нового значения, 30% предыдущего)

## Использование

### Запуск с атрибутами

```bash
cd /home/user/EvilEye
python -m evileye.main --config configs/single_video_with_attributes.json
```

### Ожидаемое поведение

1. **Детекция людей** с bbox
2. **ROI извлечение** каждые 2 кадра
3. **Классификация атрибутов** на ROI
4. **Отображение в GUI**:
   - Зелёный текст: атрибут подтверждён
   - Жёлтый текст: атрибут потерян
   - Серый текст: атрибут не детектируется

### Пример вывода в GUI

```
Person ID: 123
hard_hat: exists (0.78, 1500ms)
backpack: none (0.00, 0ms)
safety_vest: lost (0.45, 800ms)
```

## Настройка под свои нужды

### Изменение атрибутов

```json
"attrs": ["helmet", "gloves", "boots"],
"confidence_thresholds": {
  "helmet": 0.7,
  "gloves": 0.4,
  "boots": 0.5
}
```

### Изменение частоты обработки

```json
"roi": {
  "every_n_frames": 1  // Каждый кадр (больше нагрузка)
}
```

### Отключение атрибутов

```json
"classifier": {
  "enabled": false
}
```

## Требования

### Модель классификатора

- **Файл**: `models/ppe_classifier.onnx`
- **Вход**: 224x224x3 RGB изображение
- **Выход**: [hard_hat_conf, backpack_conf, safety_vest_conf]

### Видео файл

- **Путь**: `videos/planes_sample.mp4`
- **Формат**: MP4 с людьми в кадре
- **Разрешение**: любое (автоматическое масштабирование)

## Отладка

### Проверка конфигурации

```python
import json
with open('configs/single_video_with_attributes.json', 'r') as f:
    config = json.load(f)
    print("Attributes config:", config['objects_handler']['attributes_detection'])
```

### Логи атрибутов

```bash
# Проверить JSON файлы с атрибутами
ls EvilEyeData/images/2024_*/objects_*.json
```

### Производительность

- **CPU**: +15-20% при every_n_frames=2
- **Память**: +2-3MB на 100 объектов
- **FPS**: -2-3 кадра при активной обработке атрибутов


