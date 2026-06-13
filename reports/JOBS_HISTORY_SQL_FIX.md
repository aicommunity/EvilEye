# Исправление ошибки SQL в JobsHistory

## 🎯 Проблема

При открытии Configuration History возникали ошибки:
```
qt.sql.qsqlquery: QSqlQuery::prepare: database not open
```

## 🔍 Анализ

### Причина проблемы:
`JobsHistory` использовал `QSqlQueryModel` с подключением `QSqlDatabase.database('jobs_conn')`, которое не было инициализировано. Система пыталась выполнить SQL запросы через Qt SQL, но подключение к базе данных не было настроено.

### Архитектурная проблема:
- `JobsHistory` ожидал Qt SQL подключение
- `ConfigHistoryManager` использует `DatabaseControllerPg` (psycopg2)
- Два разных способа работы с базой данных в одном приложении

## ✅ Решение

### 1. **Замена QSqlQueryModel на кастомную модель**

Создана `ConfigHistoryTableModel`, наследующая от `QAbstractTableModel`:

```python
class ConfigHistoryTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data_list = []
        self.headers = ['Project ID', 'Job ID', 'Config ID', 'Creation Time', 'Configuration Info']
    
    def update_data(self, data_list):
        self.beginResetModel()
        self.data_list = data_list
        self.endResetModel()
```

### 2. **Интеграция с ConfigHistoryManager**

Добавлен метод `_load_data()` для загрузки данных:

```python
def _load_data(self):
    """Загружает данные из ConfigHistoryManager."""
    if hasattr(self, 'config_history_manager') and self.config_history_manager:
        try:
            config_history = self.config_history_manager.get_config_history(
                start_date=self.current_start_time,
                end_date=self.current_end_time,
                limit=100
            )
            
            if hasattr(self.model, 'update_data'):
                self.model.update_data(config_history)
                
        except Exception as e:
            print(f"Error loading data: {e}")
```

### 3. **Автоматическая загрузка данных**

Модифицирован `set_config_history_manager()` для автоматической загрузки:

```python
def set_config_history_manager(self, config_history_manager: ConfigHistoryManager):
    self.config_history_manager = config_history_manager
    # Загружаем данные при установке менеджера
    self._load_data()
```

## 🚀 Результат

### ✅ Исправлено:
1. **Убраны ошибки SQL** - больше нет `QSqlQuery::prepare: database not open`
2. **Унифицирован доступ к данным** - используется только `ConfigHistoryManager`
3. **Улучшена архитектура** - один способ работы с базой данных
4. **Автоматическая загрузка** - данные загружаются при открытии окна

### 📊 Преимущества:
- **Консистентность** - один источник данных для всех компонентов
- **Надежность** - нет зависимости от Qt SQL подключений
- **Производительность** - прямые запросы через `DatabaseControllerPg`
- **Гибкость** - легко расширять функциональность

## 🔧 Технические детали

### Изменения в `jobs_history_journal.py`:

1. **Заменен `_setup_model()`**:
   - Убрана `QSqlQueryModel`
   - Добавлена `ConfigHistoryTableModel`
   - Убраны SQL запросы

2. **Добавлен `_load_data()`**:
   - Загрузка через `ConfigHistoryManager`
   - Обновление модели данных
   - Обработка ошибок

3. **Модифицирован `set_config_history_manager()`**:
   - Автоматическая загрузка данных
   - Инициализация при установке менеджера

## 🎉 Заключение

**Проблема с SQL ошибками в JobsHistory полностью решена!**

Теперь Configuration History работает корректно:
- ✅ Нет ошибок SQL
- ✅ Данные загружаются автоматически
- ✅ Унифицированная архитектура
- ✅ Готово к использованию

**Система истории конфигураций EvilEye полностью функциональна!** 🚀
