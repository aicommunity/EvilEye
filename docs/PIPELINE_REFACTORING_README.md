# Pipeline Refactoring

## Обзор

Рефакторинг pipeline архитектуры для разделения общей функциональности от процессор-специфичной логики.

## Архитектура

### Иерархия классов

```
PipelineBase (abstract)
├── PipelineSimple (abstract)
│   └── PipelineCapture
└── PipelineProcessors
    └── PipelineSurveillance
```

### PipelineBase

Базовый абстрактный класс для всех pipeline реализаций.

**Абстрактные методы:**
- `get_sources() -> List` - возвращает список видео источников для внешних подписок (events, etc.)
- `generate_default_structure(num_sources: int)` - генерирует структуру конфигурации по умолчанию

**Общая функциональность:**
- Управление результатами (`_results_queue`, `_current_results`)
- Методы для работы с результатами (`add_result`, `get_results_list`, `get_current_results`, etc.)
- Управление учетными данными (`_credentials`)
- Очередь результатов с автоматическим управлением размером (maxsize=2)

### PipelineSimple

Простая реализация pipeline с абстрактным методом логики.

**Абстрактные методы:**
- `process_logic() -> Dict[str, Any]` - реализация логики обработки

**Реализованные методы:**
- `get_sources()` - возвращает пустой список (простые pipeline не имеют видео источников)
- `generate_default_structure()` - базовая реализация

### PipelineProcessors

Основная процессор-базированная pipeline, наследуется от PipelineBase.

**Реализованные методы:**
- `get_sources()` - возвращает процессоры из `sources_proc`
- `generate_default_structure()` - базовая реализация

### PipelineCapture

Простая реализация для захвата видео файла, наследуется от PipelineSimple.

**Особенности:**
- Захват видео через `VideoCapture`
- Обработка одного видео файла
- Возврат кадров в формате `CaptureImage`
- **Упрощенная инициализация**: использует параметры из секции `sources` напрямую
- **Упрощенная обработка**: использует метод `get()` из VideoCapture для чтения кадров
- **Метод `get_sources()`**: возвращает список с объектом VideoCapture

**Упрощенная архитектура:**
- `set_params_impl()`: сохраняет конфигурацию источника в `self.source_config`
- `init_impl()`: создает `VideoCapture` и передает ему `self.source_config` напрямую
- `process_logic()`: использует `self.video_capture.get()` для получения кадров
- Нет дублирования параметров - используется конфигурация как есть
- Нет ручного управления кадрами - все управляется VideoCapture

**Упрощенная обработка кадров:**
```python
def process_logic(self) -> Dict[str, Any]:
    # Get frames from VideoCapture using the get() method
    captured_images = self.video_capture.get()
    
    if not captured_images:
        return {}
    
    # Get the first (and only) captured image
    capture_image = captured_images[0]
    
    # Prepare result using data from CaptureImage
    result = {
        'source_id': capture_image.source_id,
        'frame_id': capture_image.frame_id,
        'image': capture_image,
        'timestamp': capture_image.time_stamp,
        # ... other metadata
    }
    
    return result
```

## Файловая структура

```
evileye/
├── core/
│   ├── pipeline_base.py          # PipelineBase
│   ├── pipeline_simple.py        # PipelineSimple
│   └── pipeline_processors.py    # PipelineProcessors (переименован из pipeline.py)
├── pipelines/
│   ├── pipeline_surveillance.py  # PipelineSurveillance
│   └── pipeline_capture.py       # PipelineCapture
└── samples_configs/
    └── pipeline_capture.json     # Конфигурация для PipelineCapture
```

## Миграция

### Для существующих pipeline

1. **Если pipeline наследуется от `Pipeline`:**
   - Изменить наследование на `PipelineProcessors`
   - Обновить импорты: `from evileye.core.pipeline_processors import PipelineProcessors`

2. **Если pipeline простая (без процессоров):**
   - Наследоваться от `PipelineSimple`
   - Реализовать абстрактный метод `process_logic()`

### Для новых pipeline

1. **Простая pipeline:**
   ```python
   from evileye.core.pipeline_simple import PipelineSimple
   
   class MySimplePipeline(PipelineSimple):
       def process_logic(self) -> Dict[str, Any]:
           # Реализация логики
           return result
   ```

2. **Процессор-базированная pipeline:**
   ```python
   from evileye.core.pipeline_processors import PipelineProcessors
   
   class MyProcessorPipeline(PipelineProcessors):
       # Наследует всю функциональность PipelineProcessors
       pass
   ```

## Конфигурация

### PipelineCapture

```json
{
  "pipeline": {
    "pipeline_class": "PipelineCapture"
  },
  "sources": [
    {
      "camera": "videos/sample_video.mp4",
      "source": "VideoFile",
      "source_ids": [0],
      "source_names": ["VideoCapture"],
      "split": false,
      "num_split": 0,
      "src_coords": [0],
      "loop_play": false
    }
  ]
}
```

**Упрощенная конфигурация:**
- Параметры из секции `sources` передаются напрямую в `VideoCapture`
- Нет дублирования параметров
- Более простая и понятная структура
- Поддерживает только один источник видео

### PipelineSurveillance

Полная surveillance pipeline с последовательностью процессоров:

```json
{
  "pipeline": {
    "pipeline_class": "PipelineSurveillance",
    "sources": [...],
    "preprocessors": [...],
    "detectors": [...],
    "trackers": [...],
    "mc_trackers": [...],
    "attributes_roi": [...],
    "attributes_classifier": [...]
  }
}
```

**Последовательность инициализации процессоров:**
1. Encoders (для трекинга)
2. Sources (видео источники)
3. Preprocessors (предобработка кадров)
4. Detectors (детекция объектов)
5. Trackers (трекинг объектов)
6. Multi-camera Trackers (межкамерный трекинг)
7. Attributes ROI (ROI для атрибутов)
8. Attribute Classifier (классификатор атрибутов)

## Совместимость с контроллером

Все pipeline классы должны реализовывать метод `get_sources()` для совместимости с контроллером:

- **PipelineSimple**: возвращает пустой список
- **PipelineProcessors**: возвращает процессоры из `sources_proc`
- **PipelineCapture**: возвращает список с объектом VideoCapture (с атрибутами `source_ids` и `source_names`)

## Тестирование

### Запуск тестов

```bash
# Тест базовых методов
python test_pipeline_base_methods.py

# Тест PipelineCapture get_sources
python test_pipeline_capture_sources.py

# Тест упрощенной инициализации
python test_pipeline_capture_simple.py

# Тест рефакторинга
python test_pipeline_refactoring.py
```

### Проверка совместимости

```bash
# Запуск с PipelineCapture
python evileye/process.py --config configs/pipeline_capture.json --gui --no-autoclose
```

## Преимущества рефакторинга

1. **Разделение ответственности**: общая функциональность отделена от специфичной логики
2. **Переиспользование кода**: общие методы определены в базовых классах
3. **Гибкость**: можно создавать как простые, так и сложные pipeline
4. **Совместимость**: все pipeline работают с контроллером
5. **Расширяемость**: легко добавлять новые типы pipeline
6. **Упрощение**: удален избыточный PipelineCaptureProcessors, упрощена архитектура
7. **Простота конфигурации**: PipelineCapture использует параметры источников напрямую
8. **Упрощенная обработка**: использует метод `get()` из VideoCapture для чтения кадров
9. **Автоматическое управление**: VideoCapture сам управляет кадрами и временными метками
