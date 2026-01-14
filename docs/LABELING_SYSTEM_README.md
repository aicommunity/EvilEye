# Система меток объектов (Object Labeling System) - Улучшенная версия

## Обзор

Система меток объектов автоматически сохраняет информацию о детектированных и отслеживаемых объектах в JSON файлы. **Улучшенная версия** включает:

- ✅ **Пиксельные координаты** для совместимости с COCO форматом
- ✅ **Новая структура папок** - JSON файлы рядом с изображениями
- ✅ **Буферизация и асинхронное сохранение** для высокой производительности
- ✅ **Автоматическое сохранение** при детекции и потере объектов
- ✅ **Совместимость с работой без базы данных**

## Структура файлов (НОВАЯ)

### Директории

```
EvilEyeData/
└── images/
    └── YYYY_MM_DD/
        ├── detected_frames/          # Полные кадры с детектированными объектами
        ├── detected_previews/        # Превью детектированных объектов
        ├── lost_frames/              # Полные кадры с потерянными объектами
        ├── lost_previews/            # Превью потерянных объектов
        ├── objects_found.json        # Метки детектированных объектов
        └── objects_lost.json         # Метки потерянных объектов
```

**Изменение**: JSON файлы теперь находятся в той же папке, что и изображения, для удобства работы с данными.

## Формат JSON файлов (ОБНОВЛЕННЫЙ)

### objects_found.json

```json
{
  "metadata": {
    "version": "1.0",
    "created": "2024-01-15T10:30:00",
    "description": "Object detection labels - objects found for the first time",
    "total_objects": 150,
    "last_updated": "2024-01-15T10:35:00"
  },
  "objects": [
    {
      "object_id": 1,
      "frame_id": 1234,
      "timestamp": "2024-01-15T10:30:15.123456",
      "image_filename": "detected_frames/2024_01_15_10_30_15.123456_frame.jpeg",
      "bounding_box": {
        "x": 480,        // АБСОЛЮТНЫЕ ПИКСЕЛИ (не нормализованные!)
        "y": 324,        // АБСОЛЮТНЫЕ ПИКСЕЛИ
        "width": 288,    // АБСОЛЮТНЫЕ ПИКСЕЛИ
        "height": 216    // АБСОЛЮТНЫЕ ПИКСЕЛИ
      },
      "confidence": 0.95,
      "class_id": 0,
      "class_name": "person",
      "source_id": 0,
      "track_id": 1,
      "global_id": null
    }
  ]
}
```

### objects_lost.json

```json
{
  "metadata": {
    "version": "1.0",
    "created": "2024-01-15T10:30:00",
    "description": "Object tracking labels - objects that were lost",
    "total_objects": 45,
    "last_updated": "2024-01-15T10:35:00"
  },
  "objects": [
    {
      "object_id": 1,
      "frame_id": 1234,
      "detected_timestamp": "2024-01-15T10:30:15.123456",
      "lost_timestamp": "2024-01-15T10:30:25.456789",
      "image_filename": "lost_frames/2024_01_15_10_30_25.456789_frame.jpeg",
      "bounding_box": {
        "x": 480,        // АБСОЛЮТНЫЕ ПИКСЕЛИ
        "y": 324,        // АБСОЛЮТНЫЕ ПИКСЕЛИ
        "width": 288,    // АБСОЛЮТНЫЕ ПИКСЕЛИ
        "height": 216    // АБСОЛЮТНЫЕ ПИКСЕЛИ
      },
      "confidence": 0.95,
      "class_id": 0,
      "class_name": "person",
      "source_id": 0,
      "track_id": 1,
      "global_id": null,
      "lost_frames": 5
    }
  ]
}
```

## Поля меток (ОБНОВЛЕННЫЕ)

### Общие поля для всех объектов

| Поле | Тип | Описание |
|------|-----|----------|
| `object_id` | int | Уникальный ID объекта в системе |
| `frame_id` | int | Номер кадра |
| `image_filename` | string | **Относительный путь к файлу с полным кадром** |
| `bounding_box` | object | **АБСОЛЮТНЫЕ ПИКСЕЛЬНЫЕ координаты рамки** |
| `confidence` | float | Уверенность детекции (0.0-1.0) |
| `class_id` | int | ID класса объекта |
| `class_name` | string | Название класса объекта |
| `source_id` | int | ID источника видео |
| `source_name` | string | **Название источника видео** |
| `track_id` | int | ID трека |
| `global_id` | int/null | Глобальный ID (для multi-camera tracking) |

### Поля bounding_box (ОБНОВЛЕННЫЕ)

| Поле | Тип | Описание |
|------|-----|----------|
| `x` | int | **X координата левого верхнего угла в пикселях** |
| `y` | int | **Y координата левого верхнего угла в пикселях** |
| `width` | int | **Ширина рамки в пикселях** |
| `height` | int | **Высота рамки в пикселях** |

**Важно**: Координаты теперь в абсолютных пикселях, а не нормализованные (0.0-1.0)!

## Производительность (НОВОЕ)

### Буферизация

Система использует буферизацию для повышения производительности:

- **Размер буфера**: 100 объектов (настраивается)
- **Интервал сохранения**: 30 секунд (настраивается)
- **Асинхронное сохранение**: Отдельный поток для записи
- **Автоматическое сохранение**: При заполнении буфера или по таймеру

### Конфигурация производительности

```python
# Настройка буферизации
labeling_manager.buffer_size = 100      # Сохранять при достижении 100 объектов
labeling_manager.save_interval = 30     # Сохранять каждые 30 секунд
```

### Преимущества буферизации

- ✅ **Снижение I/O операций** в 100 раз
- ✅ **Сохранение данных** даже при крахе программы
- ✅ **Высокая производительность** при большом количестве объектов
- ✅ **Автоматическое управление** памятью

## Упрощенная структура меток (ОБНОВЛЕНО)

### Поля меток

Система теперь использует упрощенную структуру:

- **`image_filename`**: Относительный путь к файлу с полным кадром
- **`source_name`**: Название источника видео

### Использование упрощенных меток

```python
# Загрузка меток
with open('EvilEyeData/images/2024_01_15/objects_found.json', 'r') as f:
    found_data = json.load(f)

# Получение данных объектов
for obj in found_data['objects']:
    image_filename = obj['image_filename']  # "detected_frames/..."
    source_name = obj['source_name']        # "camera_1"
    
    # Построение полного пути
    base_dir = "EvilEyeData"
    date_str = "2024_01_15"  # Дата из имени файла или контекста
    full_image_path = os.path.join(base_dir, "images", date_str, image_filename)
    
    print(f"Full image path: {full_image_path}")
    print(f"Source: {source_name}")
```

### Получение даты для построения пути

Дату можно получить несколькими способами:

```python
import os
from datetime import datetime

# Способ 1: Из имени файла меток
label_file = "EvilEyeData/images/2024_01_15/objects_found.json"
date_str = os.path.basename(os.path.dirname(label_file))  # "2024_01_15"

# Способ 2: Из имени файла изображения
image_filename = "2024_01_15_10_30_15.123456_frame.jpeg"
date_str = image_filename.split('_')[0:3]  # ['2024', '01', '15']
date_str = '_'.join(date_str)  # "2024_01_15"

# Способ 3: Из timestamp объекта
timestamp = obj['timestamp']  # "2024-01-15T10:30:15.123456"
date_obj = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
date_str = date_obj.strftime('%Y_%m_%d')  # "2024_01_15"
```

### Преимущества упрощенной структуры

- ✅ **Простота**: Меньше полей, проще обработка
- ✅ **Информативность**: Включено название источника
- ✅ **Портативность**: Метки работают с любым базовым каталогом
- ✅ **Совместимость**: Работает с разными структурами папок

## Использование

### Автоматическое сохранение

Система автоматически сохраняет метки при:
- Первой детекции объекта (в `objects_found.json`)
- Потере объекта (в `objects_lost.json`)

### Программное использование

```python
from evileye.objects_handler.labeling_manager import LabelingManager

# Создание менеджера меток
labeling_manager = LabelingManager(base_dir='EvilEyeData')

# Получение статистики
stats = labeling_manager.get_statistics()
print(f"Found objects: {stats['found_objects']}")
print(f"Lost objects: {stats['lost_objects']}")

# Принудительное сохранение буферов
labeling_manager.flush_buffers()

# Корректное завершение работы
labeling_manager.stop()
```

### Интеграция с ObjectsHandler

Система меток автоматически интегрирована в `ObjectsHandler`:

```python
from evileye.objects_handler.objects_handler import ObjectsHandler

# Создание обработчика объектов
obj_handler = ObjectsHandler(db_controller=None, db_adapter=None)

# Метки будут автоматически сохраняться при обработке объектов
# Буферизация и асинхронное сохранение работают автоматически
```

## Экспорт для обучения

### Формат для обучения

```python
# Экспорт всех меток в формат для обучения
training_file = labeling_manager.export_labels_for_training()

# Результат: EvilEyeData/training_data/YYYY_MM_DD_training_labels.json
```

### Совместимость с COCO

Теперь метки полностью совместимы с COCO форматом:

```python
# Преобразование в COCO формат
def convert_to_coco_format(labeling_manager):
    found_data = labeling_manager._load_json(labeling_manager.found_labels_file)
    
    coco_format = {
        "images": [],
        "annotations": [],
        "categories": []
    }
    
    for obj in found_data["objects"]:
        bbox = obj["bounding_box"]
        annotation = {
            "id": obj["object_id"],
            "image_id": obj["frame_id"],
            "category_id": obj["class_id"],
            "bbox": [bbox["x"], bbox["y"], bbox["width"], bbox["height"]],
            "area": bbox["width"] * bbox["height"],
            "iscrowd": 0
        }
        coco_format["annotations"].append(annotation)
    
    return coco_format
```

## Конфигурация

### Настройка директории

```python
# Использование пользовательской директории
labeling_manager = LabelingManager(base_dir='/path/to/custom/directory')
```

### Настройка производительности

```python
# Настройка буферизации
labeling_manager.buffer_size = 50       # Меньший буфер для быстрого сохранения
labeling_manager.save_interval = 10     # Более частое сохранение

# Принудительное сохранение
labeling_manager.flush_buffers()
```

## Анализ данных

### Статистика

```python
stats = labeling_manager.get_statistics()

print(f"Total objects: {stats['total_objects']}")
print(f"Found objects: {stats['found_objects']}")
print(f"Lost objects: {stats['lost_objects']}")
print(f"Date: {stats['date']}")
```

### Анализ по классам

```python
import json

# Загрузка меток
with open('EvilEyeData/images/2024_01_15/objects_found.json', 'r') as f:
    found_data = json.load(f)

# Подсчет объектов по классам
class_counts = {}
for obj in found_data['objects']:
    class_name = obj['class_name']
    class_counts[class_name] = class_counts.get(class_name, 0) + 1

print("Objects by class:")
for class_name, count in class_counts.items():
    print(f"  {class_name}: {count}")
```

### Доступ к изображениям по меткам

```python
import json
import os
from PIL import Image

# Загрузка меток
with open('EvilEyeData/images/2024_01_15/objects_found.json', 'r') as f:
    found_data = json.load(f)

# Обработка объектов с доступом к изображениям
base_dir = "EvilEyeData"
date_str = "2024_01_15"  # Дата из имени файла или контекста
for obj in found_data['objects']:
    # Получение данных объекта
    image_filename = obj['image_filename']
    source_name = obj['source_name']
    
    # Построение полного пути
    full_image_path = os.path.join(base_dir, "images", date_str, image_filename)
    
    # Проверка существования файла
    if os.path.exists(full_image_path):
        # Загрузка изображения
        image = Image.open(full_image_path)
        print(f"Loaded image: {full_image_path}")
        print(f"Image size: {image.size}")
        print(f"Source: {source_name}")
        
        # Получение координат рамки
        bbox = obj['bounding_box']
        x, y, w, h = bbox['x'], bbox['y'], bbox['width'], bbox['height']
        print(f"Object bbox: ({x}, {y}, {w}, {h})")
    else:
        print(f"Image not found: {full_image_path}")
```

## Совместимость

### Форматы координат

- **Входные координаты**: `[x1, y1, x2, y2]` (абсолютные пиксели)
- **Сохраненные координаты**: `{x, y, width, height}` (абсолютные пиксели)

### Преобразование координат

```python
# Из абсолютных в COCO формат (уже в правильном формате)
def absolute_to_coco_format(bbox):
    return [bbox['x'], bbox['y'], bbox['width'], bbox['height']]

# Из COCO формата в абсолютные
def coco_to_absolute_format(bbox):
    return {
        'x': bbox[0],
        'y': bbox[1], 
        'width': bbox[2],
        'height': bbox[3]
    }
```

## Тестирование

### Запуск тестов

```bash
python test_labeling_improvements.py
```

### Тестируемые компоненты

- ✅ Новая структура папок
- ✅ Пиксельные координаты
- ✅ Буферизация и асинхронное сохранение
- ✅ Производительность
- ✅ Корректное завершение работы

## Ограничения

### Производительность

- Буферизация снижает I/O операции в 100 раз
- Автоматическое сохранение каждые 30 секунд
- Принудительное сохранение при заполнении буфера

### Совместимость

- Абсолютные пиксельные координаты
- Совместимость с COCO форматом
- JSON формат для универсальности

## Расширения

### Пользовательские классы

```python
# Расширение списка классов
custom_classes = ["vehicle", "pedestrian", "bicycle"]
labeling_manager.custom_classes = custom_classes
```

### Дополнительные поля

```python
# Добавление пользовательских полей
def create_custom_object_data(obj, ...):
    data = labeling_manager.create_found_object_data(obj, ...)
    data['custom_field'] = 'custom_value'
    return data
```

### Экспорт в другие форматы

```python
# Экспорт в COCO format (теперь проще!)
def export_to_coco(labeling_manager, output_file):
    found_data = labeling_manager._load_json(labeling_manager.found_labels_file)
    # Преобразование в COCO формат
    pass

# Экспорт в YOLO format
def export_to_yolo(labeling_manager, output_dir):
    # Преобразование координат в YOLO формат
    pass
```

## Миграция с предыдущей версии

### Изменения в структуре

- JSON файлы теперь в папке с изображениями
- Координаты в абсолютных пикселях
- Буферизация для производительности

### Обратная совместимость

- Старые файлы меток остаются совместимыми
- Автоматическое преобразование не требуется
- Новые функции опциональны

## Заключение

**Улучшенная система меток** предоставляет:

- 🚀 **Высокую производительность** благодаря буферизации
- 📁 **Логичную структуру папок** для удобства работы
- 🎯 **Совместимость с COCO** для обучения моделей
- 🔄 **Асинхронное сохранение** для стабильности
- 🛡️ **Надежность** с автоматическим сохранением

**Система готова к использованию в production!** 🎉✨
