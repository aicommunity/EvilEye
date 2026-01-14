# Attributes Detection System

Система детекции и трекинга атрибутов для первичных объектов (люди, автомобили) с поддержкой вторичных атрибутов (каска, рюкзак, сумка).

## Обзор

Система позволяет:
- Детектировать атрибуты у первичных объектов через классификатор
- Отслеживать состояния атрибутов во времени (none/exists/lost)
- Применять порогирование по доверию и времени
- Отображать атрибуты в GUI с цветовой индикацией
- Сохранять данные атрибутов в JSON-логах

## Архитектура

### Компоненты

1. **RoiFeeder** - извлекает ROI из bbox первичных объектов
2. **AttributeClassifier** - классифицирует атрибуты на ROI
3. **AttributeManager** - управляет состояниями атрибутов
4. **ObjectsHandler** - интегрирует атрибуты в основной поток

### Поток данных

```
Sources → Preprocessors → Detectors → Trackers → RoiFeeder → AttributeClassifier → ObjectsHandler
                                                                                        ↓
                                                                                AttributeManager
                                                                                        ↓
                                                                                GUI/JSON Logs
```

## Конфигурация

### Основные параметры

```json
{
  "objects_handler": {
    "attributes_detection": {
      "primary_by_name": ["person", "car"],
      "primary_by_id": [0, 2],
      "secondary_by_name": ["hard_hat", "backpack"],
      "secondary_by_id": [27, 28],
      "roi": {
        "padding": 0.1,
        "size": [224, 224],
        "every_n_frames": 1
      },
      "classifier": {
        "enabled": true,
        "model": "models/ppe_classifier.onnx",
        "attrs": ["hard_hat", "backpack"],
        "confidence_thresholds": {
          "hard_hat": 0.5,
          "backpack": 0.5
        },
        "time_thresholds": {
          "hard_hat": {
            "min_time_ms": 600,
            "confirm_time_ms": 2000
          },
          "backpack": {
            "min_time_ms": 600,
            "confirm_time_ms": 2000
          }
        },
        "ema_alpha": 0.6
      }
    }
  }
}
```

### Параметры ROI

- `padding` - отступы от bbox (0.1 = 10%)
- `size` - размер кропа для классификатора [width, height]
- `every_n_frames` - частота обработки (1 = каждый кадр)

### Пороги классификатора

- `confidence_thresholds` - минимальное доверие для детекции атрибута
- `time_thresholds.min_time_ms` - время до перехода в "lost" при отсутствии детекции
- `time_thresholds.confirm_time_ms` - время для подтверждения атрибута
- `ema_alpha` - коэффициент EMA-сглаживания доверия (0.0-1.0)

## Состояния атрибутов

### FSM (Finite State Machine)

```
none → exists → lost → none
 ↑                ↓
 └────────────────┘
```

- **none** - атрибут не детектируется или не подтверждён
- **exists** - атрибут подтверждён и активен
- **lost** - атрибут перестал детектироваться, но ещё не сброшен

### Переходы

1. **none → exists**: детекция ≥ confidence_threshold в течение confirm_time_ms
2. **exists → lost**: отсутствие детекции в течение min_time_ms
3. **lost → none**: отсутствие детекции в течение confirm_time_ms
4. **lost → exists**: возобновление детекции в течение confirm_time_ms

## API

### ObjectsHandler

```python
# Передача результатов атрибутов
obj_handler.put_attributes(track_id=123, attrs={'hard_hat': 0.8, 'backpack': 0.6})

# Получение состояний атрибутов
states = obj_handler.attr_manager.get_states(track_id=123)
```

### AttributeManager

```python
# Обновление состояния атрибута
attr_manager.update(track_id, attr_name, detected, confidence, timestamp, dt_ms)

# Получение состояний для трека
states = attr_manager.get_states(track_id)
```

## JSON Формат

### Структура объекта с атрибутами

```json
{
  "object_id": 123,
  "frame_id": 456,
  "timestamp": "2024-01-15T10:30:00.000Z",
  "bounding_box": {"x": 100, "y": 200, "width": 50, "height": 80},
  "confidence": 0.85,
  "class_id": 0,
  "class_name": "person",
  "attributes": {
    "hard_hat": {
      "state": "exists",
      "confidence_smooth": 0.78,
      "frames_present": 45,
      "total_time_ms": 1500,
      "enter_count": 1,
      "last_seen_ts": 1705312200.123
    },
    "backpack": {
      "state": "none",
      "confidence_smooth": 0.0,
      "frames_present": 0,
      "total_time_ms": 0,
      "enter_count": 0,
      "last_seen_ts": null
    }
  }
}
```

### Поля атрибутов

- `state` - текущее состояние (none/exists/lost)
- `confidence_smooth` - сглаженное доверие (EMA)
- `frames_present` - количество кадров с детекцией
- `total_time_ms` - общее время присутствия в миллисекундах
- `enter_count` - количество входов в состояние "exists"
- `last_seen_ts` - timestamp последней детекции

## GUI Отображение

### Цветовая схема

- **Серый** (none) - атрибут не детектируется
- **Зелёный** (exists) - атрибут подтверждён
- **Жёлтый** (lost) - атрибут потерян, но ещё не сброшен

### Формат отображения

```
hard_hat: exists (0.78, 1500ms)
backpack: none (0.00, 0ms)
```

## Производительность

### Рекомендации

1. **ROI размер**: 224x224 оптимален для большинства классификаторов
2. **Частота обработки**: every_n_frames=1 для критичных атрибутов, 2-3 для экономии ресурсов
3. **EMA alpha**: 0.6-0.8 для баланса отзывчивости и стабильности
4. **Пороги времени**: min_time_ms=600ms, confirm_time_ms=2000ms для PPE

### Ограничения

- Максимум 100 активных объектов с атрибутами
- EMA-сглаживание требует ~1KB памяти на атрибут
- ROI-обработка добавляет ~10-20% к CPU нагрузке

## Отладка

### Логи

```bash
# Включить отладочные сообщения
export EVIL_EYE_DEBUG=1

# Проверить конфигурацию атрибутов
python -c "from evileye.controller.controller import Controller; c = Controller(); print(c.obj_handler.attr_manager)"
```

### Тестирование

```bash
# Запуск тестов атрибутов
cd /home/user/EvilEye
PYTHONPATH=/home/user/EvilEye python tests/test_attributes_detection.py
```

## Примеры использования

### PPE (Personal Protective Equipment)

```json
{
  "classifier": {
    "attrs": ["hard_hat", "safety_vest", "gloves"],
    "confidence_thresholds": {
      "hard_hat": 0.7,
      "safety_vest": 0.6,
      "gloves": 0.5
    },
    "time_thresholds": {
      "hard_hat": {"min_time_ms": 500, "confirm_time_ms": 1500},
      "safety_vest": {"min_time_ms": 800, "confirm_time_ms": 2000},
      "gloves": {"min_time_ms": 1000, "confirm_time_ms": 2500}
    }
  }
}
```

### Retail Analytics

```json
{
  "classifier": {
    "attrs": ["shopping_bag", "phone", "wallet"],
    "confidence_thresholds": {
      "shopping_bag": 0.6,
      "phone": 0.7,
      "wallet": 0.5
    }
  }
}
```

## Совместимость

- **Python**: 3.8+
- **OpenCV**: 4.0+
- **ONNX Runtime**: 1.12+
- **Процессоры**: Intel/AMD x64, ARM64 (Jetson)

## Лицензия

Система атрибутов является частью EvilEye и распространяется под той же лицензией.


