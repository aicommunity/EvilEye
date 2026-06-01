# Архитектура системы истории конфигураций EvilEye

## Обзор системы

Система истории конфигураций автоматически сохраняет все запущенные конфигурации в базе данных и предоставляет удобный интерфейс для их просмотра и восстановления.

## Компоненты системы

### 1. ConfigHistoryManager
```
┌─────────────────────────────────────┐
│        ConfigHistoryManager         │
├─────────────────────────────────────┤
│ + save_config(config, metadata)     │
│ + get_config_history(filters)       │
│ + restore_config(config_id)         │
│ + compare_configs(id1, id2)         │
│ + delete_old_configs(days)          │
│ + get_config_by_hash(hash)          │
└─────────────────────────────────────┘
```

### 2. ConfigHistoryWindow
```
┌─────────────────────────────────────┐
│        ConfigHistoryWindow          │
├─────────────────────────────────────┤
│ + show_config_list()                │
│ + filter_by_date_range()            │
│ + filter_by_name()                  │
│ + preview_config()                  │
│ + restore_config()                  │
│ + compare_configs()                 │
│ + export_history()                  │
└─────────────────────────────────────┘
```

### 3. База данных
```
┌─────────────────────────────────────┐
│           config_history            │
├─────────────────────────────────────┤
│ id (INTEGER PRIMARY KEY)            │
│ timestamp (DATETIME)                │
│ config_name (TEXT)                  │
│ config_content (TEXT)               │
│ config_hash (TEXT)                  │
│ pipeline_status (TEXT)              │
│ notes (TEXT)                        │
│ backup_created (BOOLEAN)            │
└─────────────────────────────────────┘
```

## Поток данных

### Автоматическое сохранение конфигурации
```
Controller.start_pipeline()
    ↓
ConfigHistoryManager.save_config()
    ↓
Database.insert_config_history()
    ↓
ConfigHistoryManager.generate_hash()
    ↓
Check for duplicates
    ↓
Save if unique
```

### Восстановление конфигурации
```
User clicks "Restore" in ConfigHistoryWindow
    ↓
ConfigHistoryManager.restore_config()
    ↓
Create backup of current config
    ↓
Write restored config to disk
    ↓
Notify MainWindow of config change
    ↓
Optionally restart pipeline
```

## Интеграция с существующими компонентами

### MainWindow
- Добавлен пункт меню "Configuration History"
- Статус-бар показывает последнюю конфигурацию
- Уведомления о восстановлении конфигураций

### ConfigurerMainWindow
- Кнопка "Load from History" в toolbar
- Показ истории изменений текущей конфигурации
- Автоматическое предложение восстановления при ошибках

### Controller
- Автоматическое сохранение при запуске pipeline
- Логирование статуса pipeline в историю
- Обработка ошибок с сохранением в историю

### UnifiedLauncherWindow
- Вкладка "History" с быстрым доступом
- Статистика использования конфигураций
- Последние использованные конфигурации

## События системы

### Новые события
- `config_saved_to_history` - конфигурация сохранена в историю
- `config_restored_from_history` - конфигурация восстановлена из истории
- `config_backup_created` - создана резервная копия при восстановлении
- `config_history_cleaned` - очищена старая история

### Обработчики событий
- Все окна получают уведомления о изменениях конфигураций
- Автоматическое обновление списков конфигураций
- Синхронизация состояния между окнами

## Безопасность и надежность

### Backup система
- Автоматическое создание backup при восстановлении
- Именование backup файлов с timestamp
- Возможность отката к предыдущей версии

### Валидация
- Проверка целостности конфигураций перед сохранением
- Валидация JSON структуры
- Проверка существования файлов и путей

### Очистка данных
- Автоматическая очистка старых записей (настраиваемый период)
- Сжатие больших конфигураций
- Оптимизация размера базы данных

## Пользовательский интерфейс

### ConfigHistoryWindow
```
┌─────────────────────────────────────────────────────────┐
│ Configuration History                    [X] [−] [□]    │
├─────────────────────────────────────────────────────────┤
│ Filter: [Date Range ▼] [Name ▼] [Status ▼] [Search...] │
├─────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 2024-01-15 14:30:25  poly-cameras.json  [Running]  │ │
│ │ 2024-01-15 12:15:10  single_video.json  [Stopped]  │ │
│ │ 2024-01-15 10:45:33  multi_videos.json  [Error]    │ │
│ │ 2024-01-14 16:20:15  test_config.json   [Running]  │ │
│ └─────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────┤
│ [Preview] [Restore] [Compare] [Export] [Delete]        │
└─────────────────────────────────────────────────────────┘
```

### Диалог восстановления
```
┌─────────────────────────────────────────────────────────┐
│ Restore Configuration                                   │
├─────────────────────────────────────────────────────────┤
│ Are you sure you want to restore this configuration?   │
│                                                         │
│ Config: poly-cameras.json                              │
│ Date: 2024-01-15 14:30:25                              │
│ Status: Running                                         │
│                                                         │
│ Current config will be backed up to:                   │
│ configs/poly-cameras.json.backup.20240115-143025       │
│                                                         │
│ [ ] Restart pipeline after restore                     │
│                                                         │
│ [Cancel] [Restore]                                      │
└─────────────────────────────────────────────────────────┘
```

## Конфигурация системы

### Параметры в config.json
```json
{
  "controller": {
    "auto_save_config_history": true,
    "config_history_retention_days": 30,
    "config_backup_enabled": true,
    "config_history_max_size_mb": 100
  }
}
```

### Настройки базы данных
- Автоматическое создание таблицы при первом запуске
- Индексы для быстрого поиска по дате и имени
- Оптимизация запросов для больших объемов данных

## Производительность

### Оптимизации
- Ленивая загрузка истории конфигураций
- Кэширование часто используемых конфигураций
- Сжатие старых записей
- Асинхронное сохранение в базу данных

### Мониторинг
- Логирование операций с историей
- Статистика использования конфигураций
- Мониторинг размера базы данных
- Предупреждения о превышении лимитов
