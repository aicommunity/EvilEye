# Руководство по Dependency Injection в EvilEye

## Оглавление

- [Введение](#введение)
- [Что такое Dependency Injection](#что-такое-dependency-injection)
- [DIContainer — контейнер зависимостей](#dicontainer--контейнер-зависимостей)
- [DependencyRegistry — реестр зависимостей](#dependencyregistry--реестр-зависимостей)
- [Примеры использования](#примеры-использования)
- [Сравнение с EvilEyeBase._registry](#сравнение-с-evileyebase_registry)
- [Планируемое применение](#планируемое-применение)

---

## Введение

В системе EvilEye реализован механизм Dependency Injection (DI) через два основных компонента:

- **`DIContainer`** — контейнер для управления зависимостями
- **`DependencyRegistry`** — реестр метаданных о зависимостях

**Важно:** В текущей версии эти компоненты **зарезервированы для будущего использования**. Сейчас в проекте используется `EvilEyeBase._registry` как основной механизм создания компонентов.

---

## Что такое Dependency Injection

**Dependency Injection (DI)** — это паттерн проектирования, при котором зависимости объекта предоставляются извне, а не создаются внутри самого объекта.

### Преимущества DI:

1. **Снижение связности** — компоненты не зависят от конкретных реализаций
2. **Упрощение тестирования** — легко подменять зависимости моками
3. **Централизованное управление** — все зависимости регистрируются в одном месте
4. **Управление жизненным циклом** — контроль создания и уничтожения объектов

### Пример без DI (плохо):

```python
class MyService:
    def __init__(self):
        # Прямое создание зависимостей - плохо!
        self.pipeline = PipelineSurveillance()
        self.db_service = DatabaseService()
    
    def process(self):
        self.pipeline.init()
        result = self.pipeline.process()
        self.db_service.save(result)
```

### Пример с DI (хорошо):

```python
class MyService:
    def __init__(self, pipeline: IPipeline, db_service: IDatabaseService):
        # Зависимости передаются извне - хорошо!
        self.pipeline = pipeline
        self.db_service = db_service
    
    def process(self):
        self.pipeline.init()
        result = self.pipeline.process()
        self.db_service.save(result)

# Использование с контейнером
container = DIContainer()
container.register_instance(IPipeline, PipelineSurveillance())
container.register_instance(IDatabaseService, DatabaseService())

service = MyService(
    container.get(IPipeline),
    container.get(IDatabaseService)
)
```

---

## DIContainer — контейнер зависимостей

**`DIContainer`** — это контейнер, который хранит и предоставляет сервисы по запросу. Он управляет жизненным циклом объектов и их зависимостями.

### Расположение

```python
from evileye.core.di_container import DIContainer
```

### Основные методы

#### 1. `register_instance(service_type, instance)`

Регистрирует готовый экземпляр сервиса. При каждом запросе возвращается тот же объект.

```python
container = DIContainer()

# Создаем сервис вручную
db_service = DatabaseService()
db_service.init()

# Регистрируем готовый экземпляр
container.register_instance(IDatabaseService, db_service)

# Получаем тот же экземпляр
service = container.get(IDatabaseService)
assert service is db_service  # True - тот же объект
```

**Когда использовать:**
- Когда объект уже создан и инициализирован
- Когда нужен один и тот же экземпляр для всех запросов

#### 2. `register_factory(service_type, factory)`

Регистрирует функцию-фабрику для создания сервиса. При каждом запросе создается новый экземпляр.

```python
container = DIContainer()

# Регистрируем фабрику
container.register_factory(
    IPipeline,
    lambda: PipelineSurveillance()
)

# Каждый раз создается новый экземпляр
pipeline1 = container.get(IPipeline)
pipeline2 = container.get(IPipeline)
assert pipeline1 is not pipeline2  # True - разные объекты
```

**Когда использовать:**
- Когда нужен новый экземпляр при каждом запросе
- Когда создание объекта легковесное

#### 3. `register_singleton(service_type, factory)`

Регистрирует фабрику для создания singleton. Фабрика вызывается один раз, последующие запросы возвращают тот же объект.

```python
container = DIContainer()

# Регистрируем singleton
container.register_singleton(
    IDatabaseService,
    lambda: DatabaseService()
)

# Первый запрос создает объект
service1 = container.get(IDatabaseService)

# Второй запрос возвращает тот же объект
service2 = container.get(IDatabaseService)
assert service1 is service2  # True - один и тот же объект
```

**Когда использовать:**
- Для тяжелых объектов (БД, кэши, пулы соединений)
- Когда нужен один экземпляр на все приложение

#### 4. `get(service_type) -> Optional[T]`

Получает сервис по типу. Проверяет в следующем порядке:
1. Зарегистрированные экземпляры (`_services`)
2. Singleton'ы (`_singletons`)
3. Фабрики (`_factories`)

```python
container = DIContainer()
container.register_singleton(IPipeline, lambda: PipelineSurveillance())

pipeline = container.get(IPipeline)
if pipeline is None:
    print("Сервис не зарегистрирован")
else:
    pipeline.init()
```

#### 5. `get_or_create(service_type, default_factory) -> T`

Получает сервис или создает его через фабрику по умолчанию, если сервис не зарегистрирован.

```python
container = DIContainer()

# Если сервис не зарегистрирован, создается через default_factory
pipeline = container.get_or_create(
    IPipeline,
    lambda: PipelineSurveillance()  # Фабрика по умолчанию
)
```

#### 6. `has(service_type) -> bool`

Проверяет, зарегистрирован ли сервис.

```python
if container.has(IPipeline):
    pipeline = container.get(IPipeline)
```

#### 7. `clear()`

Очищает все зарегистрированные сервисы.

```python
container.clear()  # Удаляет все регистрации
```

### Внутренняя структура

```python
class DIContainer:
    def __init__(self):
        self._services: Dict[Type, Any] = {}      # Готовые экземпляры
        self._factories: Dict[Type, Callable] = {} # Фабрики создания
        self._singletons: Dict[Type, Any] = {}     # Созданные singleton'ы
```

---

## DependencyRegistry — реестр зависимостей

**`DependencyRegistry`** — это реестр, который хранит метаданные о зависимостях (тип сервиса, фабрика создания, singleton-флаг и т.д.). Используется вместе с `DIContainer` для управления жизненным циклом сервисов.

### Расположение

```python
from evileye.core.dependencies import (
    DependencyRegistry,
    DependencyDefinition,
    get_registry,
    register_dependency
)
```

### Основные компоненты

#### DependencyDefinition

Класс, хранящий метаданные о зависимости:

```python
class DependencyDefinition:
    service_type: Type      # IPipeline, IDatabaseService и т.д.
    factory: Callable       # Функция создания
    instance: Any           # Готовый экземпляр
    singleton: bool         # Один экземпляр или каждый раз новый
```

#### DependencyRegistry

Реестр для хранения определений зависимостей:

```python
registry = DependencyRegistry()

# Регистрация зависимости
registry.register(
    service_type=IPipeline,
    factory=lambda: PipelineSurveillance(),
    singleton=True
)

# Получение определения
definition = registry.get_definition(IPipeline)
if definition:
    print(f"Singleton: {definition.singleton}")
    print(f"Factory: {definition.factory}")
```

### Глобальный реестр

Для удобства предоставлен глобальный реестр:

```python
# Получить глобальный реестр
registry = get_registry()

# Или использовать функцию-хелпер
register_dependency(
    service_type=IPipeline,
    factory=lambda: PipelineSurveillance(),
    singleton=True
)
```

### Основные методы

#### 1. `register(service_type, factory=None, instance=None, singleton=True)`

Регистрирует зависимость в реестре.

```python
registry = DependencyRegistry()

# Регистрация с фабрикой
registry.register(
    service_type=IPipeline,
    factory=lambda: PipelineSurveillance(),
    singleton=True
)

# Регистрация с готовым экземпляром
db_service = DatabaseService()
registry.register(
    service_type=IDatabaseService,
    instance=db_service,
    singleton=True
)
```

#### 2. `get_definition(service_type) -> Optional[DependencyDefinition]`

Получает определение зависимости по типу.

```python
definition = registry.get_definition(IPipeline)
if definition:
    if definition.singleton:
        print("Это singleton")
    if definition.factory:
        instance = definition.factory()
```

#### 3. `has(service_type) -> bool`

Проверяет наличие зависимости в реестре.

```python
if registry.has(IPipeline):
    definition = registry.get_definition(IPipeline)
```

#### 4. `clear()`

Очищает реестр.

```python
registry.clear()  # Удаляет все определения
```

---

## Примеры использования

### Пример 1: Базовое использование DIContainer

```python
from evileye.core.di_container import DIContainer
from evileye.core.interfaces import IPipeline, IDatabaseService
from evileye.pipelines import PipelineSurveillance
from evileye.controller.services import DatabaseService

# Создание контейнера
container = DIContainer()

# Регистрация singleton для БД сервиса
container.register_singleton(
    IDatabaseService,
    lambda: DatabaseService()
)

# Регистрация фабрики для pipeline (каждый раз новый)
container.register_factory(
    IPipeline,
    lambda: PipelineSurveillance()
)

# Использование в сервисе
class MyService:
    def __init__(self, container: DIContainer):
        self.pipeline = container.get(IPipeline)
        self.db_service = container.get(IDatabaseService)
    
    def process(self):
        self.pipeline.init()
        result = self.pipeline.process()
        self.db_service.save(result)

# Создание сервиса
service = MyService(container)
service.process()
```

### Пример 2: Использование DependencyRegistry

```python
from evileye.core.dependencies import get_registry, DependencyRegistry
from evileye.core.di_container import DIContainer
from evileye.core.interfaces import IPipeline, IDatabaseService

# Регистрация в реестре
registry = get_registry()

registry.register(
    service_type=IPipeline,
    factory=lambda: PipelineSurveillance(),
    singleton=False
)

registry.register(
    service_type=IDatabaseService,
    factory=lambda: DatabaseService(),
    singleton=True
)

# Использование реестра с контейнером
# (в будущем контейнер может автоматически читать из реестра)
container = DIContainer()

# Пока что нужно вручную регистрировать в контейнере
for service_type in [IPipeline, IDatabaseService]:
    definition = registry.get_definition(service_type)
    if definition and definition.factory:
        if definition.singleton:
            container.register_singleton(service_type, definition.factory)
        else:
            container.register_factory(service_type, definition.factory)
```

### Пример 3: Тестирование с моками

```python
from unittest.mock import Mock
from evileye.core.di_container import DIContainer
from evileye.core.interfaces import IPipeline

def test_my_service():
    # Создаем контейнер для тестов
    container = DIContainer()
    
    # Регистрируем мок вместо реального pipeline
    mock_pipeline = Mock(spec=IPipeline)
    mock_pipeline.process.return_value = {"test": "data"}
    
    container.register_instance(IPipeline, mock_pipeline)
    
    # Тестируем сервис
    service = MyService(container)
    service.process()
    
    # Проверяем вызовы
    mock_pipeline.init.assert_called_once()
    mock_pipeline.process.assert_called_once()
```

### Пример 4: Управление жизненным циклом

```python
from evileye.core.di_container import DIContainer

class Application:
    def __init__(self):
        self.container = DIContainer()
        self._setup_dependencies()
    
    def _setup_dependencies(self):
        # Регистрируем singleton для тяжелых объектов
        self.container.register_singleton(
            IDatabaseService,
            lambda: DatabaseService()
        )
        
        # Регистрируем фабрику для легковесных объектов
        self.container.register_factory(
            IPipeline,
            lambda: PipelineSurveillance()
        )
    
    def start(self):
        # Получаем зависимости
        db_service = self.container.get(IDatabaseService)
        db_service.init()
        
        pipeline = self.container.get(IPipeline)
        pipeline.init()
    
    def shutdown(self):
        # Очищаем контейнер
        self.container.clear()
```

---

## Сравнение с EvilEyeBase._registry

В текущей версии EvilEye используется два механизма создания объектов:

### EvilEyeBase._registry (текущий, активно используется)

**Назначение:** Создание компонентов pipeline через plugin-систему

**Использование:**
```python
@EvilEyeBase.register("MyDetector")
class MyDetector(EvilEyeBase):
    def init_impl(self, **kwargs):
        return True

# Создание через регистр
detector = EvilEyeBase.create_instance("MyDetector")
```

**Особенности:**
- Используется для компонентов, наследующихся от `EvilEyeBase`
- Регистрация через декоратор `@EvilEyeBase.register`
- Создание по строковому имени класса
- Активно используется в 11+ классах проекта

### DIContainer (планируется)

**Назначение:** Управление зависимостями сервисов верхнего уровня

**Использование:**
```python
container = DIContainer()
container.register_singleton(IDatabaseService, lambda: DatabaseService())
service = container.get(IDatabaseService)
```

**Особенности:**
- Используется для сервисов контроллера
- Регистрация по типу (интерфейсу)
- Поддержка singleton и factory
- Управление жизненным циклом

### Сравнительная таблица

| Характеристика | EvilEyeBase._registry | DIContainer |
|----------------|----------------------|-------------|
| **Назначение** | Компоненты pipeline | Сервисы контроллера |
| **Регистрация** | Декоратор `@register` | Методы `register_*` |
| **Поиск** | По строковому имени | По типу (Type) |
| **Singleton** | Нет | Да |
| **Factory** | Нет | Да |
| **Lifecycle** | Через EvilEyeBase | Через контейнер |
| **Статус** | Активно используется | Зарезервировано |

### Сосуществование

Оба механизма могут сосуществовать:

- **EvilEyeBase._registry** — для компонентов pipeline (детекторы, трекеры, процессоры)
- **DIContainer** — для сервисов контроллера (PipelineService, DatabaseService и т.д.)

---

## Планируемое применение

### Текущее состояние

В текущей версии EvilEye зависимости создаются напрямую в сервисах:

```python
class Controller:
    def __init__(self):
        # Прямое создание зависимостей
        self._pipeline_service = PipelineService()
        self._database_service = DatabaseService()
        self._events_service = EventsService()
```

### Планируемое использование DI

В будущих версиях планируется использовать DIContainer:

```python
class Controller:
    def __init__(self, container: DIContainer):
        # Зависимости получаются из контейнера
        self._pipeline_service = container.get(IPipelineService)
        self._database_service = container.get(IDatabaseService)
        self._events_service = container.get(IEventsService)
```

### Преимущества перехода на DI

1. **Снижение связности** — Controller не знает о конкретных реализациях
2. **Упрощение тестирования** — легко подменять сервисы моками
3. **Гибкость** — можно менять реализации без изменения Controller
4. **Централизованная конфигурация** — все зависимости в одном месте

### План миграции

1. **Этап 1:** Определить интерфейсы для сервисов (IPipelineService, IDatabaseService и т.д.)
2. **Этап 2:** Создать фабрики для сервисов
3. **Этап 3:** Зарегистрировать сервисы в DIContainer
4. **Этап 4:** Обновить Controller для использования контейнера
5. **Этап 5:** Обновить тесты для использования моков

---

## Заключение

DIContainer и DependencyRegistry предоставляют мощный механизм для управления зависимостями в системе EvilEye. Хотя они пока зарезервированы для будущего использования, их архитектура позволяет:

- Снизить связность между компонентами
- Упростить тестирование
- Централизованно управлять зависимостями
- Гибко управлять жизненным циклом объектов

При переходе на DI важно помнить, что `EvilEyeBase._registry` остается основным механизмом для компонентов pipeline, а `DIContainer` будет использоваться для сервисов верхнего уровня.

---

## См. также

- [Архитектура системы](ARCHITECTURE.md) — раздел "Дополнительные паттерны: DI и фасады"
- [Разделение ответственности: EvilEyeBase и Protocols](ARCHITECTURE.md#разделение-ответственности-evileyebase-и-protocols)
- [evileye.core.di_container](../evileye/core/di_container.py) — исходный код DIContainer
- [evileye.core.dependencies](../evileye/core/dependencies.py) — исходный код DependencyRegistry
