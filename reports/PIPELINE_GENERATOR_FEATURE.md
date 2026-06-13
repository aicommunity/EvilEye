# Pipeline Generator Feature

## Обзор

Добавлена функциональность автоматического поиска и генерации pipeline классов в контроллере EvilEye. Система теперь может динамически обнаруживать и создавать экземпляры pipeline классов по их имени.

## Функциональность

### Автоматическое обнаружение Pipeline классов

Система автоматически ищет pipeline классы в следующих местах:

1. **Пакет `evileye.pipelines`** - встроенные pipeline классы
2. **Локальная папка `pipelines/`** - пользовательские pipeline классы в текущей рабочей директории

### Генератор Pipeline классов

Контроллер теперь включает методы для:
- Поиска всех доступных pipeline классов
- Создания экземпляров pipeline по имени класса
- Интеграции с системой создания конфигураций

## Реализация

### Новые методы в контроллере

#### `_discover_pipeline_classes()`
```python
def _discover_pipeline_classes(self):
    """Discover all pipeline classes from packages and current directory"""
    pipeline_classes = {}
    
    # Search in evileye.pipelines package
    # Search in current working directory pipelines folder
    
    return pipeline_classes
```

#### `_create_pipeline_instance(pipeline_class_name)`
```python
def _create_pipeline_instance(self, pipeline_class_name: str):
    """Create pipeline instance by class name"""
    pipeline_classes = self._discover_pipeline_classes()
    
    if pipeline_class_name not in pipeline_classes:
        available_classes = list(pipeline_classes.keys())
        raise ValueError(f"Pipeline class '{pipeline_class_name}' not found. Available classes: {available_classes}")
    
    pipeline_class = pipeline_classes[pipeline_class_name]
    return pipeline_class()
```

#### `get_available_pipeline_classes()`
```python
def get_available_pipeline_classes(self):
    """Get list of available pipeline classes"""
    return list(self._discover_pipeline_classes().keys())
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
    
    # ... rest of the method
```

## Интеграция с CLI

### Новая команда `--list-pipelines`

```bash
evileye-create --list-pipelines
```

**Вывод:**
```
Available pipeline classes:
========================================
1. PipelineSurveillance
2. TestPipeline

Total: 2 pipeline class(es)

Use --pipeline <class_name> to specify a pipeline when creating a configuration.
```

### Использование конкретного Pipeline

```bash
evileye-create my_config --sources 2 --pipeline PipelineSurveillance
evileye-create my_config --sources 1 --pipeline TestPipeline
```

## Примеры использования

### 1. Создание пользовательского Pipeline

**Создайте файл `pipelines/my_pipeline.py`:**

```python
from evileye.core.pipeline_processors import Pipeline
from evileye.core.processor_source import ProcessorSource
from evileye.core.processor_step import ProcessorStep
from typing import Dict, List


class MyPipeline(Pipeline):
    """Custom pipeline implementation"""

    def __init__(self):
        super().__init__()

    def init_impl(self, **kwargs):
        """Initialize custom pipeline"""
        pipeline_params = self.params

        # Initialize only sources for simplicity
        self._init_sources(pipeline_params.get("sources", []), self._credentials)
        return True

    def _init_sources(self, params: List[Dict], credentials: Dict):
        """Initialize source processors"""
        if not params:
            return

        num_sources = len(params)
        sources_proc = ProcessorSource(
            processor_name="sources",
            class_name="VideoCapture",
            num_processors=num_sources,
            order=0
        )

        sources_proc.set_params(params)
        sources_proc.init()
        self._add_processor(sources_proc)
        self.sources_proc = sources_proc
```

**Создайте файл `pipelines/__init__.py`:**
```python
from .my_pipeline import MyPipeline

__all__ = ['MyPipeline']
```

### 2. Использование пользовательского Pipeline

```bash
# Список доступных pipeline классов
evileye-create --list-pipelines

# Создание конфигурации с пользовательским pipeline
evileye-create custom_config --sources 2 --pipeline MyPipeline
```

## Обработка ошибок

### Pipeline класс не найден
```bash
evileye-create test --pipeline NonExistentPipeline
```

**Вывод:**
```
Warning: Could not create pipeline 'NonExistentPipeline': 
Pipeline class 'NonExistentPipeline' not found. 
Available classes: ['PipelineSurveillance', 'TestPipeline']

Falling back to default pipeline
```

### Ошибки импорта
Система корректно обрабатывает ошибки импорта и продолжает работу с доступными pipeline классами.

## Преимущества

1. **Расширяемость:** Легко добавлять новые pipeline классы
2. **Гибкость:** Поддержка как встроенных, так и пользовательских pipeline
3. **Автоматическое обнаружение:** Не требует регистрации pipeline классов
4. **Обратная совместимость:** Работает с существующими конфигурациями
5. **Обработка ошибок:** Graceful fallback при ошибках

## Тестирование

### Успешно протестировано:

1. ✅ Поиск встроенных pipeline классов
2. ✅ Поиск пользовательских pipeline классов
3. ✅ Создание экземпляров pipeline по имени
4. ✅ Обработка несуществующих pipeline классов
5. ✅ Интеграция с `evileye-create`
6. ✅ Создание конфигураций с разными pipeline

## Результат

**Pipeline Generator функциональность успешно добавлена!**

Система теперь поддерживает динамическое создание pipeline классов и интеграцию с системой создания конфигураций.



