# Исправление проблемы с индексами в Pipeline

## Проблема

В коде `evileye/pipelines/pipeline_surveillance.py` в методе `generate_default_structure` использовалось умножение списков `* num_sources`, что приводило к созданию ссылок на один и тот же объект. В результате все источники, детекторы и трекеры получали одинаковые параметры с последним индексом.

### Проблемный код:
```python
def generate_default_structure(self, num_sources: int):
    params = {
        "sources": [
            {
                "source": "IpCamera",
                "camera": "rtsp://url",
                "width": 1920,
                "height": 1080,
                "fps": 30
            }
        ] * num_sources,  # ❌ Проблема: создает ссылки на один объект
        "detectors": [{}] * num_sources,  # ❌ Проблема: создает ссылки на один объект
        "trackers": [{}] * num_sources,   # ❌ Проблема: создает ссылки на один объект
    }

    for i in range(num_sources):
        params["sources"][i].update(dict({"source_ids": [i], "source_names": [f"Cam{i}"]}))
        params["detectors"][i].update(dict({"source_ids": [i]}))
        params["trackers"][i].update(dict({"source_ids": [i]}))
```

**Результат:** Все источники получали `source_ids=[2]` и `source_names=['Cam2']` для 3 источников.

## Решение

Заменили умножение списков на list comprehension, что создает отдельные объекты для каждого индекса:

### Исправленный код:
```python
def generate_default_structure(self, num_sources: int):
    params = {
        "sources": [
            {
                "source": "IpCamera",
                "camera": "rtsp://url",
                "width": 1920,
                "height": 1080,
                "fps": 30,
                "source_ids": [i],           # ✅ Правильно: уникальный индекс
                "source_names": [f"Cam{i}"]  # ✅ Правильно: уникальное имя
            }
            for i in range(num_sources)     # ✅ Используем list comprehension
        ],
        "detectors": [
            {
                "source_ids": [i]           # ✅ Правильно: уникальный индекс
            }
            for i in range(num_sources)     # ✅ Используем list comprehension
        ],
        "trackers": [
            {
                "source_ids": [i]           # ✅ Правильно: уникальный индекс
            }
            for i in range(num_sources)     # ✅ Используем list comprehension
        ],
        "mc_trackers": [
            {
                "source_ids": list(range(num_sources)),
                "enable": False
            }
        ]
    }

    self.set_params(**params)
    self.init()
```

## Результат

### До исправления (3 источника):
```json
{
  "sources": [
    {"source_ids": [2], "source_names": ["Cam2"]},  // ❌ Неправильно
    {"source_ids": [2], "source_names": ["Cam2"]},  // ❌ Неправильно
    {"source_ids": [2], "source_names": ["Cam2"]}   // ❌ Неправильно
  ]
}
```

### После исправления (3 источника):
```json
{
  "sources": [
    {"source_ids": [0], "source_names": ["Cam0"]},  // ✅ Правильно
    {"source_ids": [1], "source_names": ["Cam1"]},  // ✅ Правильно
    {"source_ids": [2], "source_names": ["Cam2"]}   // ✅ Правильно
  ]
}
```

## Тестирование

### Успешно протестировано:

1. ✅ Создание конфигурации с 3 источниками
2. ✅ Проверка уникальности индексов для источников
3. ✅ Проверка уникальности индексов для детекторов
4. ✅ Проверка уникальности индексов для трекеров
5. ✅ Проверка уникальности имен источников

### Результат тестирования:
```
Number of sources: 3
Number of detectors: 3
Number of trackers: 3

Sources:
  Source 0: source_ids=[0], source_names=['Cam0']
  Source 1: source_ids=[1], source_names=['Cam1']
  Source 2: source_ids=[2], source_names=['Cam2']

Detectors:
  Detector 0: source_ids=[0]
  Detector 1: source_ids=[1]
  Detector 2: source_ids=[2]

Trackers:
  Tracker 0: source_ids=[0]
  Tracker 1: source_ids=[1]
  Tracker 2: source_ids=[2]

✅ All indexes are correctly set!
```

## Преимущества исправления

1. **Правильная индексация:** Каждый источник получает уникальный индекс
2. **Уникальные имена:** Каждый источник получает уникальное имя
3. **Корректная работа:** Детекторы и трекеры правильно привязаны к источникам
4. **Масштабируемость:** Работает для любого количества источников
5. **Читаемость:** Код стал более понятным и безопасным

## Заключение

Проблема с индексами успешно исправлена. Теперь каждый источник, детектор и трекер получает правильный уникальный индекс, что обеспечивает корректную работу системы с несколькими источниками.



