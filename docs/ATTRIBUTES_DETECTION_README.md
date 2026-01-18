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

1. **none → exists**: 
   - Детекция ≥ confidence_threshold в течение confirm_time_ms
   - ИЛИ found_ratio ≥ 70% (интеллектуальное решение)
2. **exists → lost**: 
   - Отсутствие детекции в течение min_time_ms
   - ИЛИ found_ratio < 70% и ≥ 30% (интеллектуальное решение)
3. **lost → none**: 
   - Отсутствие детекции в течение confirm_time_ms
   - ИЛИ found_ratio < 30% (интеллектуальное решение)
4. **lost → exists**: 
   - Возобновление детекции в течение confirm_time_ms
   - ИЛИ found_ratio ≥ 70% (интеллектуальное решение)

### Улучшенная логика состояний

Система использует интеллектуальную логику принятия решений на основе статистических данных:

**Новые метрики:**
- `total_found_time_ms` - суммарное время обнаружения атрибута
- `total_lost_time_ms` - суммарное время потери атрибута
- `found_ratio` - отношение времени обнаружения к общему времени: `total_found_time_ms / (total_found_time_ms + total_lost_time_ms)`

**Пороги принятия решений:**

| Found Ratio | Состояние | Описание |
|-------------|-----------|----------|
| ≥ 70% | `exists` | Атрибут стабильно присутствует |
| 30-70% | `lost` | Атрибут нестабилен, частично присутствует |
| < 30% | `none` | Атрибут практически отсутствует |

**Преимущества:**
- Статистический подход: решения принимаются на основе исторических данных
- Устойчивость к шуму: кратковременные потери не влияют на общее состояние
- Адаптивность: система учитывает паттерны поведения атрибутов
- Меньше переключений: состояния не меняются при каждом кадре

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
- `total_found_time_ms` - суммарное время обнаружения атрибута
- `total_lost_time_ms` - суммарное время потери атрибута
- `found_ratio` - отношение времени обнаружения к общему времени (0.0-1.0)
- `enter_count` - количество входов в состояние "exists"
- `last_seen_ts` - timestamp последней детекции
- `no_detect_time_ms` - время с последней детекции

## GUI Отображение

### Цветовая схема

- **Серый** (`none`) - атрибут не детектируется или не подтверждён
- **Зелёный** (`exists`) - атрибут подтверждён и активен
- **Жёлтый** (`lost`) - атрибут перестал детектироваться, но ещё не сброшен

### Формат отображения

```
hard_hat: exists (0.78, 1500ms, 80.0%)
no_hard_hat: lost (0.12, 0ms, 20.0%)
```

### Расшифровка цифр в GUI

Формат: `attr_name: state (confidence_smooth, summary_time_ms, found_ratio%)`

1. **Состояние** (`state`):
   - `none` - атрибут не обнаружен или сброшен
   - `exists` - атрибут подтверждён и активен
   - `lost` - атрибут был обнаружен, но потерян

2. **Сглаженное доверие** (`confidence_smooth`) - первое число в скобках:
   - EMA-сглаженное значение confidence от детекции
   - Диапазон: 0.00 - 1.00
   - При детекции: `new_confidence = α * yolo_confidence + (1-α) * old_confidence`
   - При отсутствии: **НЕ изменяется** (сохраняется последнее значение)
   - α (ema_alpha): настраивается в конфигурации (рекомендуется 0.6-0.8)
   - Преимущество: Стабильность - confidence не затухает при временном отсутствии детекции

3. **Суммарное время** (`summary_time_ms`) - второе число в скобках:
   - Рассчитывается как `max(0, total_found_time_ms - total_lost_time_ms)`
   - Показывает чистое время присутствия атрибута
   - Сбрасывается при переходе в состояние `none`

4. **Found ratio** (`found_ratio%`) - третье число в скобках:
   - Процент времени обнаружения: `total_found_time_ms / (total_found_time_ms + total_lost_time_ms) * 100`
   - Показывает, какую долю времени атрибут был обнаружен
   - Используется для принятия решений о состоянии

### Масштабирование шрифта

Размер текста атрибутов автоматически масштабируется в зависимости от разрешения изображения:

- **640x480**: font_scale ≈ 0.24 (маленький текст)
- **1280x720**: font_scale ≈ 0.36 (средний текст)  
- **1920x1080**: font_scale ≈ 0.53 (базовый размер)
- **2560x1440**: font_scale ≈ 0.71 (большой текст)
- **3840x2160**: font_scale ≈ 1.07 (очень большой текст)

Настройка масштабирования:

```json
"text_config": {
  "font_scale_method": "resolution_based",
  "base_resolution": [1920, 1080],
  "font_size_pt": 12
}
```

### Примеры интерпретации

**Пример 1**: `hard_hat: exists (0.78, 1500ms, 80.0%)`
- Состояние: Атрибут подтверждён и активен
- Доверие: 78% (высокое, стабильное)
- Время: 1.5 секунды чистого присутствия
- Found ratio: 80% времени атрибут был обнаружен

**Пример 2**: `no_hard_hat: lost (0.12, 0ms, 20.0%)`
- Состояние: Атрибут был обнаружен, но потерян
- Доверие: 12% (низкое)
- Время: 0ms (сброшено при переходе в `lost`)
- Found ratio: 20% времени атрибут был обнаружен

**Пример 3**: `backpack: none (0.00, 0ms, 0.0%)`
- Состояние: Атрибут не обнаружен
- Доверие: 0% (полностью затухло)
- Время: 0ms (сброшено)
- Found ratio: 0% (атрибут практически отсутствует)

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


