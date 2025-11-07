# Тесты EvilEye

Структурированная система тестов для проекта EvilEye.

## Структура

Тесты разделены на два основных типа:

- **Unit тесты** (`unit/`) - тестируют отдельные классы и методы изолированно
- **Integration тесты** (`integration/`) - тестируют взаимодействие компонентов

### Организация по модулям

Тесты организованы по модулям проекта:

```
tests/
├── unit/                          # Unit тесты
│   ├── capture/                  # Video capture
│   │   ├── gstreamer/
│   │   ├── opencv/
│   │   └── video_file/
│   ├── detection/                # Object detection
│   ├── tracking/                 # Object tracking
│   │   └── botsort/
│   ├── attributes/               # Attributes detection
│   ├── events/                   # Events detectors
│   │   ├── zone/
│   │   ├── cam/
│   │   ├── fov/
│   │   ├── system/
│   │   └── attribute/
│   ├── database/                 # Database adapters
│   │   ├── postgresql/
│   │   └── json/
│   ├── pipeline/                 # Pipeline classes
│   ├── roi/                      # ROI functionality
│   ├── preprocessing/           # Preprocessing
│   ├── registry/                 # Class registry
│   ├── text_rendering/          # Text rendering
│   └── labeling/                 # Labeling system
├── integration/                  # Integration тесты
│   ├── capture/                  # Video capture integration
│   │   ├── gstreamer/
│   │   ├── opencv/
│   │   └── video_file/
│   ├── detection/                # Detection integration
│   ├── tracking/                 # Tracking integration
│   ├── attributes/               # Attributes integration
│   ├── events/                   # Events integration
│   ├── database/                 # Database integration
│   │   ├── postgresql/
│   │   └── json/
│   ├── journal/                  # Journal/GUI integration
│   ├── pipeline/                 # Pipeline integration
│   ├── image_saving/            # Image saving integration
│   └── controller/              # Controller integration
├── run_all_tests.py             # Запуск всех тестов
├── run_unit_tests.py            # Запуск unit тестов
├── run_integration_tests.py     # Запуск integration тестов
├── generate_tests_docs.py      # Генерация документации
└── conftest.py                  # Общие pytest fixtures
```

## Запуск тестов

### Все тесты

```bash
# Запуск всех тестов
python3 tests/run_all_tests.py

# С verbose выводом
python3 tests/run_all_tests.py -v

# С покрытием кода
python3 tests/run_all_tests.py --coverage

# Только unit тесты
python3 tests/run_all_tests.py --type unit

# Только integration тесты
python3 tests/run_all_tests.py --type integration

# Тесты конкретной категории
python3 tests/run_all_tests.py --category capture
```

### Unit тесты

```bash
# Все unit тесты
python3 tests/run_unit_tests.py

# С verbose выводом
python3 tests/run_unit_tests.py -v

# Параллельно (требует pytest-xdist)
python3 tests/run_unit_tests.py -p

# Тесты конкретной категории
python3 tests/run_unit_tests.py --category pipeline
```

### Integration тесты

```bash
# Все integration тесты
python3 tests/run_integration_tests.py

# С verbose выводом
python3 tests/run_integration_tests.py -v

# Тесты конкретной категории
python3 tests/run_integration_tests.py --category capture

# С маркерами
python3 tests/run_integration_tests.py -m "slow or database"
```

### Прямой запуск через pytest

```bash
# Все тесты
pytest tests/

# Только unit тесты
pytest tests/unit/

# Только integration тесты
pytest tests/integration/

# Конкретная категория
pytest tests/integration/capture/

# Конкретный тест
pytest tests/unit/pipeline/test_pipeline_base_methods.py
```

## Критерии разделения

### Unit тесты

- Тестируют отдельные классы/методы изолированно
- Используют моки для внешних зависимостей
- Быстрые, не требуют внешних ресурсов
- Примеры: `test_attributes_detection.py`, `test_roi_core.py`, `test_pipeline_base_methods.py`

### Integration тесты

- Тестируют взаимодействие компонентов
- Могут использовать реальные файлы, БД, сеть
- Медленнее, требуют настройки окружения
- Примеры: `test_gstreamer_rtsp_connection.py`, `test_journal_simple.py`, `test_image_saving.py`

## Документация

Документация тестов генерируется автоматически:

```bash
python3 tests/generate_tests_docs.py
```

Это создаст следующие файлы:

- `TESTS_DOCUMENTATION.md` - полная документация всех тестов
- `TESTS_INDEX.md` - индекс тестов по модулям
- `TESTS_COVERAGE.md` - отчет о покрытии модулей тестами

## Требования

- Python 3.8+
- pytest
- pytest-xdist (опционально, для параллельного запуска)
- pytest-cov (опционально, для покрытия кода)

## Использование pytest

Все тесты используют pytest как единый фреймворк тестирования.

### Примеры pytest тестов

**Простой тест:**
```python
def test_something():
    assert 1 + 1 == 2
```

**Тест с fixture:**
```python
@pytest.fixture
def my_fixture():
    return SomeObject()

def test_with_fixture(my_fixture):
    assert my_fixture.property == "value"
```

**Тест с параметрами:**
```python
@pytest.mark.parametrize("input,expected", [(1, 2), (2, 4)])
def test_multiply(input, expected):
    assert input * 2 == expected
```

### Fixtures

Общие fixtures доступны в `conftest.py`:
- `project_root_path` - путь к корню проекта
- `test_data_dir` - директория с тестовыми данными
- `sample_configs_dir` - директория с примерами конфигураций
- `evil_eye_data_dir` - директория EvilEyeData
- `mock_db_controller` - моковый DB контроллер
- `mock_db_adapter` - моковый DB адаптер

## Примечания

- Приоритет исправления: если тест не работает, сначала проверяем код на баги
- Устаревшие тесты обновляются или удаляются если функциональность изменилась
- Баги в тестах исправляются если проблема в самом тесте

