# Централизованная система управления классами

## Обзор

Реализована централизованная система управления классами через `ClassManager`, которая решает проблемы с разрозненностью информации о классах в системе.

## Проблемы, которые решает система

### ❌ **Старые проблемы:**
1. **Порядок инициализации**: `model_class_mapping` создается после загрузки модели, но `classes` обрабатывается до загрузки
2. **Разрозненность данных**: Разные компоненты используют разные источники информации о классах
3. **Отсутствие централизации**: Нет единого места для управления классами
4. **Конфликты**: Нет системы обнаружения и разрешения конфликтов между детекторами

### ✅ **Новые возможности:**
1. **Централизованное управление**: Единый `ClassManager` для всех компонентов
2. **Автоматическое разрешение**: Автоматическое обновление `classes` после получения `model_class_mapping`
3. **Обнаружение конфликтов**: Автоматическое обнаружение и отчет о конфликтах
4. **Гибкость**: Поддержка как имен классов, так и ID в конфигурациях

## Архитектура системы

```
┌─────────────────────────────────────────────────────────────────┐
│                    CENTRALIZED CLASS SYSTEM                     │
├─────────────────────────────────────────────────────────────────┤
│  Controller.class_manager (ClassManager)                        │
│  ├── Collects mappings from all sources                        │
│  ├── Resolves conflicts                                        │
│  ├── Provides unified class information                        │
│  └── Updates all components                                   │
├─────────────────────────────────────────────────────────────────┤
│  Sources of class information:                                 │
│  ├── ObjectDetectorBase.model_class_mapping                    │
│  ├── AttributeClassifier.class_mapping                        │
│  └── Manual configuration                                      │
├─────────────────────────────────────────────────────────────────┤
│  Components using class information:                           │
│  ├── ObjectDetectorBase.classes (filtering)                    │
│  ├── ObjectsHandler.primary_by_name/by_id                     │
│  ├── Visualizer.class_mapping (display)                       │
│  └── AttributeClassifier.class_mapping                         │
└─────────────────────────────────────────────────────────────────┘
```

## Основные компоненты

### 1. ClassManager
**Файл**: `evileye/core/class_manager.py`

**Ответственности:**
- Сбор class mappings от всех источников
- Разрешение конфликтов между источниками
- Предоставление единой информации о классах
- Поддержка конвертации между именами и ID

**Основные методы:**
```python
# Добавление mapping от источника
add_class_mapping(mapping: Dict[str, int], source: str) -> bool

# Конвертация classes параметра
convert_classes_to_ids(classes: List[Union[str, int]]) -> List[int]
convert_classes_to_names(classes: List[Union[str, int]]) -> List[str]

# Получение информации о классах
get_class_id(class_name: str) -> Optional[int]
get_class_name(class_id: int) -> Optional[str]
get_class_mapping() -> Dict[str, int]

# Работа с primary классами
get_primary_classes_by_name(primary_by_name: List[str]) -> List[int]
get_primary_classes_by_id(primary_by_id: List[int]) -> List[int]
```

### 2. ObjectDetectorBase
**Обновления:**
- Добавлен `class_manager` атрибут
- Метод `set_class_manager()` для установки ClassManager
- Обновлен `_process_classes_parameter()` для использования ClassManager
- Автоматическое обновление `classes` после получения `model_class_mapping`

### 3. Controller
**Обновления:**
- Инициализация `ClassManager` в конструкторе
- Обновлен `update_class_mapping_from_detectors()` для использования ClassManager
- Передача ClassManager во все компоненты

### 4. ObjectsHandler
**Обновления:**
- Поддержка ClassManager в `_is_primary_object()`
- Автоматическая конвертация primary классов через ClassManager

## Примеры использования

### 1. Использование имен классов в конфигурации
```json
{
  "detectors": [
    {
      "model": "models/yolov8n.pt",
      "classes": ["person", "car", "bicycle", "truck"],
      "source_ids": [0]
    }
  ],
  "objects_handler": {
    "attributes_detection": {
      "primary_by_name": ["person"],
      "primary_by_id": []
    }
  }
}
```

### 2. Смешанное использование
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

### 3. Программное использование
```python
# Получение class_id по имени
class_id = controller.class_manager.get_class_id("person")  # 0

# Получение имени по class_id
class_name = controller.class_manager.get_class_name(0)  # "person"

# Конвертация classes параметра
classes_ids = controller.class_manager.convert_classes_to_ids(["person", "car"])  # [0, 2]

# Получение primary классов
primary_ids = controller.class_manager.get_primary_classes_by_name(["person"])  # [0]
```

## Процесс работы системы

### 1. Инициализация
```
Controller.__init__() 
├── self.class_manager = ClassManager()
└── self.class_mapping = default_mapping
```

### 2. Загрузка pipeline
```
Controller.init()
├── pipeline.init()
├── detectors.init()
├── models.load()
└── model_class_mapping.extract()
```

### 3. Обновление class_mapping
```
Controller.update_class_mapping_from_detectors()
├── Collect mappings from all detectors
├── Add to ClassManager with conflict detection
├── Update controller.class_mapping
├── Update visualizer.class_mapping
└── Set class_manager for all components
```

### 4. Обработка classes параметра
```
ObjectDetectorBase._process_classes_parameter()
├── Check if ClassManager available
├── Convert classes using ClassManager
└── Update classes with resolved IDs
```

## Обнаружение конфликтов

### Типы конфликтов:
1. **Конфликт имен**: Один класс имеет разные ID в разных детекторах
2. **Конфликт ID**: Один ID соответствует разным именам классов

### Примеры конфликтов:
```
⚠️  Class mapping conflicts detected:
   - Class 'person' has different IDs: 0 vs 1 (sources: ObjectDetectorYolo vs ObjectDetectorRtdetr)
   - Class ID 0 has different names: 'person' vs 'bicycle' (sources: ObjectDetectorYolo vs AttributeClassifier)
Using first occurrence for each class name/ID pair.
```

## Преимущества новой системы

### 1. **Централизация**
- Единое место для управления классами
- Согласованность между компонентами
- Упрощение отладки и мониторинга

### 2. **Автоматизация**
- Автоматическое обновление после загрузки моделей
- Автоматическое разрешение конфликтов
- Автоматическая конвертация между форматами

### 3. **Гибкость**
- Поддержка как имен классов, так и ID
- Смешанное использование в конфигурациях
- Обратная совместимость

### 4. **Надежность**
- Обнаружение конфликтов
- Валидация входных данных
- Fallback к старым методам

## Обратная совместимость

- **Старые конфигурации** с `classes: [0, 1, 2]` продолжают работать
- **Новые конфигурации** с `classes: ["person", "car"]` поддерживаются
- **Fallback логика** при отсутствии ClassManager
- **Постепенная миграция** компонентов

## Файлы, требующие обновления

### Новые файлы:
- `evileye/core/class_manager.py` - централизованный менеджер классов

### Обновленные файлы:
- `evileye/object_detector/object_detection_base.py` - поддержка ClassManager
- `evileye/controller/controller.py` - интеграция ClassManager
- `evileye/objects_handler/objects_handler.py` - использование ClassManager

### Примеры конфигураций:
- `configs/example_classes_system.json` - полный пример с именами классов
- `configs/example_classes_by_names.json` - простой пример
- `configs/example_class_mapping.json` - с class_mapping

## Заключение

Новая централизованная система управления классами решает все основные проблемы:

1. ✅ **Проблема порядка инициализации** - ClassManager автоматически обновляет classes после получения model_class_mapping
2. ✅ **Разрозненность данных** - единый источник истины для всех компонентов
3. ✅ **Отсутствие централизации** - ClassManager как центральный компонент
4. ✅ **Конфликты** - автоматическое обнаружение и разрешение

Система стала более надежной, гибкой и удобной в использовании! 🎯


