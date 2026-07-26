# Автоматическое обновление class_mapping из детекторов

## Обзор изменений

Реализована система автоматического обновления `class_mapping` в Controller на основе информации о классах, извлеченной из загруженных моделей детекторов.

## Основные изменения

### 1. ObjectDetectorBase
- **Поддержка имен классов**: Параметр `classes` теперь поддерживает как ID классов `[0, 1, 2]`, так и имена классов `["person", "car", "bicycle"]`
- **Автоматическая конвертация**: Имена классов автоматически конвертируются в ID при наличии `model_class_mapping`
- **Метод `_process_classes_parameter()`**: Обрабатывает параметр `classes` и определяет тип (ID или имена)
- **Метод `update_classes_from_model_mapping()`**: Обновляет `classes` после получения `model_class_mapping`

### 2. DetectionThreadBase
- **Метод `_update_model_class_mapping_from_model()`**: Абстрактный метод для обновления mapping из модели
- **Автоматическое обновление**: Вызывается после загрузки модели в `init_detection_implementation()`

### 3. DetectionThreadYolo
- **Реализация `_update_model_class_mapping_from_model()`**: Извлекает `model.names` и создает mapping
- **Автоматическое обновление**: После загрузки YOLO модели

### 4. DetectionThreadRtdetr
- **Реализация `_update_model_class_mapping_from_model()`**: Извлекает `model.names` и создает mapping
- **Автоматическое обновление**: После загрузки RTDETR модели

### 5. DetectionThreadRfdetr
- **Реализация `_update_model_class_mapping_from_model()`**: Извлекает `model.class_names` или `model.names`
- **Автоматическое обновление**: После загрузки RFDETR модели

### 6. Controller
- **Метод `update_class_mapping_from_detectors()`**: Собирает mapping от всех детекторов
- **Обнаружение конфликтов**: Проверяет на конфликты между детекторами
- **Автоматическое обновление**: Вызывается после инициализации pipeline
- **Обновление visualizer**: Передает обновленный mapping в visualizer

## Примеры использования

### Использование имен классов в конфигурации
```json
{
  "detectors": [
    {
      "model": "models/yolov8n.pt",
      "classes": ["person", "car", "bicycle", "truck"],
      "source_ids": [0]
    }
  ]
}
```

### Использование ID классов (как раньше)
```json
{
  "detectors": [
    {
      "model": "models/yolov8n.pt",
      "classes": [0, 2, 3, 7],
      "source_ids": [0]
    }
  ]
}
```

### Смешанное использование (не рекомендуется)
```json
{
  "detectors": [
    {
      "model": "models/yolov8n.pt",
      "classes": ["person", 2, "bicycle", 7],
      "source_ids": [0]
    }
  ]
}
```

## Автоматическое обновление class_mapping

### Процесс обновления:
1. **Инициализация pipeline** - загружаются все детекторы
2. **Загрузка моделей** - каждый детектор загружает свою модель
3. **Извлечение mapping** - извлекается `model_class_mapping` из каждой модели
4. **Сбор mapping** - Controller собирает все mapping от детекторов
5. **Обнаружение конфликтов** - проверяются конфликты между детекторами
6. **Обновление Controller** - обновляется `controller.class_mapping`
7. **Обновление Visualizer** - передается обновленный mapping в visualizer

### Обнаружение конфликтов:
- **Конфликт имен**: Один класс имеет разные ID в разных детекторах
- **Конфликт ID**: Один ID соответствует разным именам классов
- **Предупреждения**: Все конфликты выводятся в консоль

## Преимущества

1. **Автоматизация**: Не нужно вручную настраивать `class_mapping`
2. **Гибкость**: Поддержка как ID, так и имен классов
3. **Совместимость**: Обратная совместимость с существующими конфигурациями
4. **Обнаружение ошибок**: Автоматическое обнаружение конфликтов
5. **Удобство**: Можно использовать понятные имена классов в конфигурации

## Обратная совместимость

- **Старые конфигурации** с `classes: [0, 1, 2]` продолжают работать
- **Новые конфигурации** с `classes: ["person", "car", "bicycle"]` поддерживаются
- **Автоматическое обновление** `class_mapping` происходит прозрачно
- **Fallback** к старым значениям при отсутствии mapping

## Примеры вывода в консоль

### Успешное обновление:
```
Updated model_class_mapping from YOLO model: {'person': 0, 'bicycle': 1, 'car': 2, ...}
Auto-updated model_class_mapping from detection thread: {'person': 0, 'bicycle': 1, ...}
Found class mapping from detector: {'person': 0, 'bicycle': 1, ...}
✅ Updated controller class_mapping with 80 classes from 1 detectors
✅ Updated visualizer class_mapping
```

### Обнаружение конфликтов:
```
⚠️  Class mapping conflicts detected:
   - Class 'person' has different IDs: 0 vs 1
   - Class ID 0 has different names: 'person' vs 'bicycle'
Using first occurrence for each class name/ID pair.
```

### Предупреждения:
```
Warning: Class names provided but no model_class_mapping available: ['person', 'car']
Warning: Some class names not found in model mapping: ['unknown_class']
```

## Файлы, требующие обновления

Если у вас есть существующие конфигурации, они продолжат работать без изменений. Для новых проектов рекомендуется использовать имена классов для лучшей читаемости.

Примеры обновленных конфигураций:
- `configs/example_classes_by_names.json` - использование имен классов
- `configs/example_class_mapping.json` - использование class_mapping


