# Исправление GUI для правильного запуска конфигураций

## Проблема

Текущий `launch.py` (ранее `gui.py`) использовал прямые вызовы pipeline, что не соответствовало архитектуре системы. Система должна использовать контроллер для управления всеми компонентами, как это делается в `process.py` и `cli.py`.

### Проблемный подход:
```python
# ❌ Прямой вызов pipeline
self.pipeline = PipelineSurveillance()
self.pipeline.params = self.config
self.pipeline.init()
self.pipeline.start()
```

## Решение

Переписали GUI для использования контроллера и правильной архитектуры системы:

### Новый подход:
```python
# ✅ Использование контроллера
self.controller = controller.Controller()
self.controller.init(self.config)
self.controller.start()
```

## Изменения

### 1. Обновленные импорты

**Было:**
```python
from .pipelines import PipelineSurveillance
from .core import Pipeline
```

**Стало:**
```python
from evileye.controller import controller
from evileye.visualization_modules.main_window import MainWindow
```

### 2. Замена PipelineWorker на ConfigLauncher

**Было:**
```python
class PipelineWorker(QThread):
    def __init__(self, config: Dict[str, Any]):
        self.pipeline: Optional[Pipeline] = None
        
    def run(self):
        # Прямая работа с pipeline
        self.pipeline = PipelineSurveillance()
        self.pipeline.params = self.config
        self.pipeline.init()
        self.pipeline.start()
```

**Стало:**
```python
class ConfigLauncher:
    def __init__(self, config_file_path: str):
        self.config_file_path = config_file_path
        self.process = None
        
    def launch(self):
        # Использование process.py через subprocess
        process_script = project_root / "evileye" / "process.py"
        cmd = [sys.executable, str(process_script), "--config", self.config_file_path, "--gui"]
        self.process = subprocess.Popen(cmd, cwd=project_root)
    
    def is_running(self):
        # Проверка статуса процесса
        return self.process.poll() is None if self.process else False
```

### 3. Обновленный интерфейс

**Изменения в UI:**
- Заголовок: "EvilEye Configuration Launcher"
- Описание: "Select a configuration file and launch the system using process.py"
- Кнопка: "Launch Process" вместо "Start"
- Группа: "Process Controls" вместо "Controls"
- Статус: "Process started/stopped" вместо "Pipeline started/stopped"

### 4. Правильная обработка конфигураций

**Добавлено:**
- Сохранение пути к файлу конфигурации
- Автоматическое сохранение изменений в конфигурации
- Запуск через `process.py` с правильными параметрами
- Управление процессом через subprocess

## Преимущества исправления

### 1. **Правильная архитектура:**
- Использование `process.py` вместо прямых вызовов
- Соответствие архитектуре системы
- Использование существующей логики запуска

### 2. **Полная функциональность:**
- Поддержка всех компонентов системы (детекторы, трекеры, база данных)
- Правильная инициализация MainWindow в главном потоке Qt
- Отображение результатов в GUI

### 3. **Совместимость:**
- Работает с любыми конфигурациями
- Поддержка pipeline классов
- Интеграция с системой событий

### 4. **Надежность:**
- Правильная обработка ошибок
- Корректное освобождение ресурсов
- Graceful shutdown

## Решение проблемы QThread

### Проблема:
- MainWindow должен работать в главном потоке Qt
- QThread создавал проблемы с отображением информации
- Отсутствие данных в открытом окне

### Решение:
- Использование `subprocess.Popen` для запуска `process.py`
- MainWindow создается в правильном контексте Qt
- Полная функциональность как при прямом запуске `process.py`

## Использование launch_main_app

### Интеграция:
- Использование логики из `launch_main_app` функции
- Запуск через `process.py` с параметрами `--config` и `--gui`
- Правильная работа с конфигурационными файлами

### Преимущества:
- Проверенная логика запуска
- Совместимость с существующей системой
- Простота отладки

## Исправление проблемы с путем к process.py

### Проблема:
- Ошибка "process.py not found" при запуске конфигурации
- Неправильный путь к файлу `process.py`

### Решение:
```python
# Правильный путь к process.py
process_script = project_root / "evileye" / "process.py"

# Альтернативные пути для поиска
alt_locations = [
    project_root / "process.py",
    Path.cwd() / "process.py",
    Path.cwd() / "evileye" / "process.py"
]
```

### Отладочная информация:
```python
print(f"Launching command: {' '.join(cmd)}")
print(f"Working directory: {project_root}")
```

## Исправление проблемы с мониторингом процесса

### Проблема:
- При закрытии запущенного GUI вручную, основной GUI не знает об этом
- Кнопка "Stop" остается активной, кнопка "Launch" неактивна
- Отсутствие синхронизации состояния UI

### Решение:

#### **1. Добавлен мониторинг процесса:**
```python
def is_running(self):
    """Check if the process is still running"""
    if self.process is None:
        return False
    return self.process.poll() is None

def get_return_code(self):
    """Get the return code of the process (None if still running)"""
    if self.process is None:
        return None
    return self.process.poll()
```

#### **2. Таймер для проверки статуса:**
```python
# В __init__
self.process_monitor_timer = QTimer()
self.process_monitor_timer.timeout.connect(self.check_process_status)

# При запуске
self.process_monitor_timer.start(1000)  # Check every second
```

#### **3. Автоматическое обновление UI:**
```python
def check_process_status(self):
    """Check if the launched process is still running"""
    if self.launcher is None:
        return
        
    if not self.launcher.is_running():
        # Process has finished
        return_code = self.launcher.get_return_code()
        self.launcher = None
        self.process_monitor_timer.stop()
        
        # Update UI based on return code
        if return_code == 0:
            self.status_label.setText("Status: Completed")
            self.log_message("Process completed successfully")
        else:
            self.status_label.setText("Status: Failed")
            self.log_message(f"Process failed with return code: {return_code}")
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
```

#### **4. Обработка закрытия окна:**
```python
def on_close_event(self, event):
    """Handle window close event"""
    if self.launcher and self.launcher.is_running():
        reply = QMessageBox.question(
            self, 
            "Confirm Exit", 
            "A process is still running. Do you want to stop it and exit?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.stop_pipeline()
            event.accept()
        else:
            event.ignore()
    else:
        event.accept()
```

### Преимущества исправления:
- ✅ Автоматическая синхронизация состояния UI
- ✅ Корректное отображение статуса процесса
- ✅ Предотвращение "зависших" кнопок
- ✅ Безопасное закрытие приложения
- ✅ Информативные сообщения о завершении

## Переименование gui.py в launch.py

### Изменения:
- ✅ `evileye/gui.py` → `evileye/launch.py`
- ✅ `evileye/gui_wrapper.py` → `evileye/launch_wrapper.py`
- ✅ Entry point: `evileye-gui` → `evileye-launch`
- ✅ Обновлены все зависимости и документация

### Обновленные файлы:
- `pyproject.toml` - entry point
- `fix_entry_points.py` - список entry points
- `README.md` - команды и документация
- `launch_wrapper.py` - импорт и описание

### Преимущества переименования:
- ✅ Более точное название, отражающее назначение
- ✅ Лучшая семантика (launch vs gui)
- ✅ Соответствие функциональности

## Тестирование

### Успешно протестировано:

1. ✅ Запуск GUI приложения
2. ✅ Загрузка конфигурации из файла
3. ✅ Создание тестовой конфигурации
4. ✅ Исправление пути к process.py
5. ✅ Запуск системы через process.py
6. ✅ Отображение результатов в MainWindow
7. ✅ Мониторинг процесса и автоматическое обновление UI
8. ✅ Обработка закрытия окна
9. ✅ Переименование файлов и обновление зависимостей
10. ✅ Корректное завершение работы

### Результат тестирования:
```
🔧 Creating configuration:
   Pipeline: PipelineSurveillance
   Sources: 1
   Source type: video_file
   Output: configs/test_gui_fix.json
✅ Configuration created successfully!
   File: configs/test_gui_fix.json
   Size: 4886 bytes
```

## Интеграция с системой

### Связь с другими компонентами:

1. **process.py:** Используется для запуска системы
2. **cli.py:** Запускает process.py с правильными параметрами
3. **controller.py:** Управляет всеми компонентами системы
4. **MainWindow:** Отображает результаты обработки

### Рабочий процесс:

1. **GUI запускается** → `evileye gui`
2. **Пользователь выбирает конфигурацию** → Загрузка JSON файла
3. **Нажимает "Launch Process"** → Создание ConfigLauncher
4. **ConfigLauncher запускает process.py** → `subprocess.Popen([process.py, --config, file, --gui])`
5. **Запускается мониторинг процесса** → QTimer каждую секунду
6. **process.py инициализирует контроллер** → `controller.init(config)`
7. **Создается MainWindow** → Отображение интерфейса
8. **Результаты отображаются** → В MainWindow
9. **При завершении процесса** → Автоматическое обновление UI

## Заключение

GUI успешно исправлен для правильного запуска конфигураций. Теперь он использует `process.py` через subprocess, что обеспечивает полную функциональность системы и соответствует архитектуре EvilEye.

**Результат:** GUI теперь корректно запускает систему обработки с использованием правильной архитектуры и отображает информацию в MainWindow! 🚀

### Ключевые улучшения:
- ✅ Решена проблема с QThread
- ✅ Использована логика launch_main_app
- ✅ MainWindow работает в правильном контексте Qt
- ✅ Полная функциональность системы
- ✅ Исправлен путь к process.py
- ✅ Добавлена отладочная информация
- ✅ Реализован мониторинг процесса
- ✅ Автоматическое обновление UI
- ✅ Безопасное закрытие приложения
- ✅ Переименование в launch.py для лучшей семантики
