# Pipeline Class Initialization Feature

## Обзор

Добавлена функциональность автоматического выбора pipeline класса в контроллере на основе параметра `pipeline_class` в конфигурации. Контроллер теперь может динамически создавать экземпляры pipeline классов при инициализации.

## Функциональность

### Автоматический выбор Pipeline класса

Контроллер теперь автоматически:
1. **Читает параметр `pipeline_class`** из `params['pipeline']['pipeline_class']`
2. **Создает экземпляр указанного pipeline класса** с помощью pipeline генератора
3. **Возвращается к PipelineSurveillance по умолчанию** если pipeline класс не найден или не указан
4. **Выводит предупреждения** о выборе pipeline класса

### Обратная совместимость

- Конфигурации без `pipeline_class` продолжают работать
- Используется `PipelineSurveillance` по умолчанию
- Выводится предупреждение о использовании pipeline по умолчанию

## Реализация

### Обновленный метод `init` в контроллере

```python
def init(self, params):
    self.params = params
    
    # ... credentials loading ...
    
    # Initialize processing pipeline with automatic class selection
    pipeline_params = self.params.get("pipeline", {})
    pipeline_class_name = pipeline_params.get("pipeline_class")
    
    if pipeline_class_name:
        try:
            self.pipeline = self._create_pipeline_instance(pipeline_class_name)
            print(f"Using pipeline class: {pipeline_class_name}")
        except Exception as e:
            print(f"Warning: Could not create pipeline '{pipeline_class_name}': {e}")
            print("Falling back to default PipelineSurveillance")
            self.pipeline = PipelineSurveillance()
    else:
        print("Warning: No pipeline_class specified in pipeline parameters, using default PipelineSurveillance")
        self.pipeline = PipelineSurveillance()
    
    self.pipeline.set_credentials(self.credentials)
    self.pipeline.set_params(**pipeline_params)
    self.pipeline.init()
    
    # ... rest of initialization ...
```

### Обновленный метод `create_config`

```python
def create_config(self, num_sources: int, pipeline_class: str | None):
    """Create configuration with specified pipeline class"""
    self.init({})
    
    # Create pipeline instance if class name is provided
    if pipeline_class:
        try:
            self.pipeline = self._create_pipeline_instance(pipeline_class)
            print(f"Created pipeline instance: {pipeline_class}")
        except Exception as e:
            print(f"Warning: Could not create pipeline '{pipeline_class}': {e}")
            print("Falling back to default pipeline")
            self.pipeline = PipelineSurveillance()
    else:
        # Use default pipeline
        self.pipeline = PipelineSurveillance()
    
    config_data = {}
    self.update_params()
    
    # Get parameters safely, avoiding non-serializable objects
    raw_params = self.get_params()
    config_data = {}
    
    # Copy only serializable parameters
    for key, value in raw_params.items():
        if key == 'pipeline':
            # Handle pipeline parameters specially
            pipeline_params = {}
            if isinstance(value, dict):
                for p_key, p_value in value.items():
                    if not p_key.startswith('_') and not callable(p_value):
                        pipeline_params[p_key] = p_value
            config_data[key] = pipeline_params
        elif isinstance(value, dict):
            # Copy other dictionaries
            config_data[key] = value.copy()
        elif not callable(value) and not key.startswith('_'):
            # Copy other serializable values
            config_data[key] = value
    
    # Add pipeline_class to pipeline configuration only if explicitly specified
    if 'pipeline' in config_data and pipeline_class:
        config_data['pipeline']['pipeline_class'] = pipeline_class
    
    # ... rest of configuration creation ...
```

## Примеры использования

### 1. Конфигурация с pipeline классом

**configs/my_config.json:**
```json
{
  "pipeline": {
    "pipeline_class": "PipelineSurveillance",
    "sources": [
      {
        "camera": "video_1.mp4",
        "source": "VideoFile",
        "source_ids": [0],
        "source_names": ["Source 1"]
      }
    ]
  }
}
```

**Результат:**
```
Using pipeline class: PipelineSurveillance
```

### 2. Конфигурация без pipeline класса

**configs/default_config.json:**
```json
{
  "pipeline": {
    "sources": [
      {
        "camera": "video_1.mp4",
        "source": "VideoFile",
        "source_ids": [0],
        "source_names": ["Source 1"]
      }
    ]
  }
}
```

**Результат:**
```
Warning: No pipeline_class specified in pipeline parameters, using default PipelineSurveillance
```

### 3. Конфигурация с несуществующим pipeline классом

**configs/invalid_config.json:**
```json
{
  "pipeline": {
    "pipeline_class": "NonExistentPipeline",
    "sources": []
  }
}
```

**Результат:**
```
Warning: Could not create pipeline 'NonExistentPipeline': Pipeline class 'NonExistentPipeline' not found. Available classes: ['PipelineSurveillance']
Falling back to default PipelineSurveillance
```

## Интеграция с CLI

### Создание конфигураций с pipeline классом

```bash
# Создание с явно указанным pipeline классом
evileye-create my_config --sources 2 --pipeline PipelineSurveillance

# Создание без указания pipeline класса (используется по умолчанию)
evileye-create default_config --sources 1
```

### Результат создания конфигураций

**С pipeline классом:**
```json
{
  "pipeline": {
    "pipeline_class": "PipelineSurveillance",
    "sources": [...]
  }
}
```

**Без pipeline класса:**
```json
{
  "pipeline": {
    "sources": [...]
  }
}
```

## Обработка ошибок

### Типы ошибок и их обработка

1. **Pipeline класс не найден:**
   - Выводится предупреждение с доступными классами
   - Используется PipelineSurveillance по умолчанию

2. **Ошибка создания экземпляра:**
   - Выводится предупреждение с деталями ошибки
   - Используется PipelineSurveillance по умолчанию

3. **Параметр pipeline_class отсутствует:**
   - Выводится предупреждение
   - Используется PipelineSurveillance по умолчанию

### Безопасная сериализация

Добавлена безопасная сериализация параметров в JSON:
- Исключаются несериализуемые объекты
- Исключаются приватные атрибуты (начинающиеся с `_`)
- Исключаются вызываемые объекты (`callable`)

## Преимущества

1. **Гибкость:** Поддержка различных pipeline классов
2. **Обратная совместимость:** Существующие конфигурации продолжают работать
3. **Автоматическое обнаружение:** Использует pipeline генератор
4. **Информативность:** Понятные сообщения о выборе pipeline
5. **Надежность:** Graceful fallback при ошибках
6. **Безопасность:** Защита от несериализуемых объектов

## Тестирование

### Успешно протестировано:

1. ✅ Инициализация с указанным pipeline классом
2. ✅ Инициализация без pipeline класса (fallback)
3. ✅ Обработка несуществующих pipeline классов
4. ✅ Создание конфигураций с pipeline классом
5. ✅ Создание конфигураций без pipeline класса
6. ✅ Безопасная сериализация в JSON
7. ✅ Интеграция с pipeline генератором

## Результат

**Pipeline Class Initialization функциональность успешно добавлена!**

Контроллер теперь автоматически выбирает и создает pipeline классы на основе конфигурации, обеспечивая гибкость и обратную совместимость.



