# Руководство по рефакторингу GUI EvilEye

## Обзор

Данный документ описывает проведенный рефакторинг GUI системы EvilEye, включая новую архитектуру, компоненты и способы их использования.

## Архитектура GUI системы

### Основные компоненты

#### 1. WindowManager (`window_manager.py`)
Централизованный менеджер для управления всеми окнами GUI приложения.

**Функциональность:**
- Регистрация и отслеживание всех открытых окон
- Централизованное управление жизненным циклом окон
- Координация взаимодействия между окнами
- Сохранение/восстановление состояния окон (позиция, размер)
- Система событий для синхронизации состояния

**Основные методы:**
```python
# Регистрация окна
window_manager.register_window(window_id, window_type, window_instance, config_file)

# Управление состоянием
window_manager.set_window_state(window_id, WindowState.OPEN)
window_manager.set_unsaved_changes(window_id, True)

# Получение информации
window_manager.get_window(window_id)
window_manager.get_windows_by_type("configurer")
```

#### 2. BaseWindow и BaseMainWindow (`base_window.py`)
Базовые классы для всех окон GUI приложения.

**BaseWindow** - для обычных окон (QWidget)
**BaseMainWindow** - для главных окон (QMainWindow)

**Функциональность:**
- Интеграция с WindowManager
- Обработка событий закрытия с проверкой несохраненных изменений
- Сохранение/восстановление геометрии окна
- Управление состоянием окна

**Абстрактные методы для переопределения:**
```python
@abstractmethod
def get_config_data(self) -> Optional[Dict[str, Any]]:
    """Получить данные конфигурации для сохранения"""

@abstractmethod
def apply_config_data(self, config_data: Dict[str, Any]) -> bool:
    """Применить данные конфигурации"""
```

#### 3. Диалоги (`dialogs/`)
Набор диалоговых окон для различных операций.

**SaveConfirmationDialog** - диалог подтверждения сохранения при закрытии окна
**SaveAsDialog** - диалог "Сохранить как"
**ConfigRestoreDialog** - диалог восстановления конфигураций из истории
**ConfigCompareDialog** - диалог сравнения конфигураций

#### 4. ROI Editor (`roi_editor_window.py`)
Независимое окно для редактирования ROI (Regions of Interest).

**История развития:**
- Преобразован из диалогового окна (`ROIEditorDialog`) в полноценное окно (`ROIWindow`)
- Исправлены проблемы зависания при открытии и загрузке ROI
- Оптимизировано обновление сцены для улучшения производительности

**Функциональность:**
- Редактирование ROI из детекторов
- Визуализация ROI на canvas
- Сохранение и загрузка ROI из конфигурации
- Интеграция с детекторами для получения текущих ROI

**Использование:**
```python
# Открытие ROI Editor из MainWindow
main_window.open_roi_editor()

# Загрузка ROI из детектора
roi_window.set_rois_from_detector(detector)
```

#### 5. Events Journal (`events_journal_json.py`)
Журнал событий с поддержкой JSON и базы данных.

**История развития:**
- Унифицирована структура таблицы с DatabaseJournalWindow
- Исправлено отображение изображений и временных меток
- Добавлено обновление в реальном времени
- Исправлено масштабирование bounding boxes

**Функциональность:**
- Отображение событий found и lost
- Превью изображений для событий
- Фильтрация по времени и типу события
- Поддержка двойного клика для открытия полного изображения
- Совместимость с JSON и database режимами

**Структура таблицы:**
- Колонки: `['Event', 'Time', 'Time lost', 'Information', 'Preview', 'Lost preview']`
- Группировка found и lost событий в одной строке
- Автоматическое обновление каждые 5 секунд

### Рефакторированные окна

#### 1. ConfigurerMainWindow
Окно настроек/конфигурирования с улучшенной функциональностью.

**Новые возможности:**
- Отслеживание изменений в реальном времени
- Диалог подтверждения сохранения при закрытии
- Валидация конфигурации перед сохранением
- Кнопка "Save As..." для сохранения под новым именем
- Автоматическое обновление заголовка окна при наличии изменений

**Использование:**
```python
# Создание окна настроек
configurer = ConfigurerMainWindow(
    config_file_name="configs/my_config.json",
    win_width=1280,
    win_height=720,
    parent=parent_window
)

# Отслеживание изменений
configurer.set_unsaved_changes(True)

# Сохранение конфигурации
configurer.save_config()
configurer.save_config_as()
```

#### 2. MainWindow
Главное окно визуализации с интеграцией настроек.

**Новые возможности:**
- Меню "Settings" для открытия окна настроек
- Модальное окно настроек
- Обработка изменений конфигурации
- Предложение перезапуска при изменении критических параметров

**Использование:**
```python
# Открытие окна настроек
main_window.open_settings_window()

# Обработка изменений конфигурации
main_window._on_settings_config_changed(config_file)
```

#### 3. UnifiedLauncherWindow
Единое окно-лаунчер для выбора режима работы.

**Функциональность:**
- Выбор режима: Configure / Run
- Выбор файла конфигурации
- История последних конфигураций
- Предпросмотр конфигурации
- Быстрый запуск с последней конфигурацией

**Использование:**
```python
# Создание лаунчера
launcher = UnifiedLauncherWindow()

# Запуск в режиме настройки
launcher.current_mode = "configure"
launcher._launch_configurer()

# Запуск приложения
launcher.current_mode = "run"
launcher._launch_application()
```

## Система событий

### Типы событий

```python
# События WindowManager
window_opened = pyqtSignal(str, str)  # window_id, window_type
window_closed = pyqtSignal(str, str)  # window_id, window_type
window_state_changed = pyqtSignal(str, WindowState)  # window_id, new_state
config_changed = pyqtSignal(str)  # config_file_path
pipeline_started = pyqtSignal()
pipeline_stopped = pyqtSignal()
zone_added = pyqtSignal(int, str)  # source_id, zone_type
zone_removed = pyqtSignal(int, str)  # source_id, zone_type
database_connected = pyqtSignal()
database_disconnected = pyqtSignal()
```

### Регистрация обработчиков событий

```python
# Регистрация обработчика
window_manager.register_event_handler("config_changed", my_handler)

# Отправка события
window_manager.emit_event("config_changed", config_file_path)
```

## Интеграция с существующим кодом

### Запуск приложения

#### Старый способ:
```bash
evileye-launch  # Запускает EvilEyeGUI
```

#### Новый способ:
```bash
evileye-launch --unified  # Запускает UnifiedLauncherWindow
evileye-launch -u         # Короткая форма
```

### Создание нового окна

```python
from evileye.visualization_modules.base_window import BaseMainWindow
from evileye.visualization_modules.window_manager import get_window_manager

class MyWindow(BaseMainWindow):
    def __init__(self, parent=None):
        super().__init__(
            window_id="my_window",
            window_type="custom",
            config_file="configs/my_config.json",
            parent=parent
        )
        
        # Ваша инициализация
        self._init_ui()
    
    def get_config_data(self) -> Optional[Dict[str, Any]]:
        # Возвращаем данные для сохранения
        return {"my_data": "value"}
    
    def apply_config_data(self, config_data: Dict[str, Any]) -> bool:
        # Применяем загруженные данные
        return True
```

## Конфигурация

### Параметры WindowManager

```json
{
  "controller": {
    "use_dispatcher_window": false,
    "auto_save_interval": 30000,
    "max_recent_configs": 10
  }
}
```

### Состояние окон

Состояние всех окон автоматически сохраняется в файл `gui_state.json`:

```json
{
  "configurer_main": {
    "window_type": "configurer",
    "state": "open",
    "geometry": {
      "x": 100,
      "y": 100,
      "width": 1280,
      "height": 720
    },
    "config_file": "configs/my_config.json",
    "metadata": {}
  }
}
```

## Миграция существующих окон

### Шаг 1: Наследование от BaseWindow/BaseMainWindow

```python
# Было
class MyWindow(QMainWindow):
    def __init__(self):
        super().__init__()

# Стало
class MyWindow(BaseMainWindow):
    def __init__(self, parent=None):
        super().__init__(
            window_id="my_window",
            window_type="custom",
            config_file=None,
            parent=parent
        )
```

### Шаг 2: Реализация абстрактных методов

```python
def get_config_data(self) -> Optional[Dict[str, Any]]:
    """Получить данные конфигурации для сохранения"""
    return {
        "window_geometry": {
            "x": self.x(),
            "y": self.y(),
            "width": self.width(),
            "height": self.height()
        },
        "custom_data": self.my_data
    }

def apply_config_data(self, config_data: Dict[str, Any]) -> bool:
    """Применить данные конфигурации"""
    try:
        geometry = config_data.get("window_geometry", {})
        if geometry:
            self.setGeometry(
                geometry.get("x", 100),
                geometry.get("y", 100),
                geometry.get("width", 800),
                geometry.get("height", 600)
            )
        
        self.my_data = config_data.get("custom_data", {})
        return True
    except Exception as e:
        self.logger.error(f"Error applying config: {e}")
        return False
```

### Шаг 3: Интеграция с WindowManager

```python
def __init__(self, parent=None):
    super().__init__(...)
    
    # Регистрация в WindowManager происходит автоматически
    # Дополнительная настройка при необходимости
    self.window_manager.register_event_handler(
        "config_changed", 
        self._on_config_changed
    )
```

## Лучшие практики

### 1. Управление состоянием

- Всегда используйте `set_unsaved_changes()` для отслеживания изменений
- Сохраняйте состояние в `get_config_data()`
- Восстанавливайте состояние в `apply_config_data()`

### 2. Обработка ошибок

```python
def save_config(self, file_path: Optional[str] = None) -> bool:
    try:
        # Логика сохранения
        return True
    except Exception as e:
        self.logger.error(f"Error saving config: {e}")
        QMessageBox.critical(
            self, 
            "Ошибка сохранения", 
            f"Не удалось сохранить конфигурацию:\n{str(e)}"
        )
        return False
```

### 3. Логирование

```python
# Используйте модульный логгер
self.logger = get_module_logger("my_window")

# Логируйте важные события
self.logger.info("Window opened")
self.logger.debug("Configuration loaded")
self.logger.error("Failed to save config")
```

### 4. Сигналы и слоты

```python
# Подключайте сигналы в конструкторе
self.some_widget.valueChanged.connect(self._on_value_changed)

# Используйте @pyqtSlot() для слотов
@pyqtSlot()
def _on_value_changed(self):
    self.set_unsaved_changes(True)
```

## Тестирование

### Создание тестов для WindowManager

```python
import unittest
from PyQt6.QtWidgets import QApplication
from evileye.visualization_modules.window_manager import WindowManager

class TestWindowManager(unittest.TestCase):
    def setUp(self):
        self.app = QApplication([])
        self.manager = WindowManager()
    
    def test_register_window(self):
        # Тест регистрации окна
        pass
    
    def test_window_state_management(self):
        # Тест управления состоянием
        pass
```

### Тестирование отслеживания изменений

```python
def test_unsaved_changes_tracking(self):
    window = MyWindow()
    
    # Проверяем начальное состояние
    self.assertFalse(window.has_unsaved_changes())
    
    # Вносим изменения
    window.set_unsaved_changes(True)
    self.assertTrue(window.has_unsaved_changes())
    
    # Сохраняем
    window.save_config()
    self.assertFalse(window.has_unsaved_changes())
```

## Устранение неполадок

### Частые проблемы

#### 1. Окно не регистрируется в WindowManager
**Решение:** Убедитесь, что наследуетесь от BaseWindow/BaseMainWindow

#### 2. Не работают диалоги сохранения
**Решение:** Проверьте, что вызываете `set_unsaved_changes(True)` при изменениях

#### 3. Ошибки при сохранении конфигурации
**Решение:** Проверьте реализацию `get_config_data()` и обработку исключений

### Отладка

```python
# Включите отладочное логирование
import logging
logging.getLogger("evileye.window_manager").setLevel(logging.DEBUG)

# Проверьте состояние WindowManager
status = window_manager.get_status_summary()
print(f"Windows: {status['total_windows']}")
print(f"Unsaved changes: {status['unsaved_changes_count']}")
```

## Заключение

Рефакторинг GUI системы EvilEye обеспечивает:

- ✅ Централизованное управление окнами
- ✅ Единообразную обработку событий
- ✅ Автоматическое отслеживание изменений
- ✅ Улучшенный пользовательский опыт
- ✅ Расширяемую архитектуру

Новая архитектура готова к дальнейшему развитию и добавлению новых функций.
