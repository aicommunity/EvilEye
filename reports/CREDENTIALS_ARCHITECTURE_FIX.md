# Исправление архитектуры credentials EvilEye

## 🎯 Проблема

Была допущена ошибка в понимании архитектуры credentials EvilEye:

1. **Credentials были добавлены в `database_config.json`** - неправильно
2. **Не был создан файл `credentials.json`** - отсутствовал
3. **Нарушена логика разделения** конфигурации и credentials

## 🔍 Анализ правильной архитектуры

### Логика загрузки credentials в `controller.py`:

```python
# 1. Загружаются credentials из credentials.json
try:
    with open("credentials.json") as creds_file:
        self.credentials = json.load(creds_file)
except FileNotFoundError as ex:
    pass

# 2. Загружается database_config.json
with open(os.path.join(os.path.dirname(__file__), "..", "database_config.json")) as data_config_file:
    self.database_config = json.load(data_config_file)

# 3. Credentials используются как значения по умолчанию
database_creds = self.credentials.get("database", None)
if not database_creds:
    database_creds = dict()

# 4. Устанавливаются значения по умолчанию для credentials
database_creds["user_name"] = database_creds.get("user_name", "postgres")
database_creds["password"] = database_creds.get("password", "")
# ... и так далее

# 5. Credentials переопределяют значения в database_config
self.database_config["database"]["user_name"] = self.database_config["database"].get("user_name", database_creds["user_name"])
self.database_config["database"]["password"] = self.database_config["database"].get("password", database_creds["password"])
# ... и так далее
```

### Правильная архитектура:

1. **`credentials.json`** - содержит чувствительные данные (пароли, токены)
2. **`database_config.json`** - содержит техническую конфигурацию БД
3. **Основная конфигурация** - может переопределить любые настройки

## ✅ Исправление

### 1. **Очищен `database_config.json`**

Удалены credentials, оставлена только техническая конфигурация:

```json
{
    "database": {
        "type": "sqlite",
        "database_name": "/home/user/EvilEye/EvilEyeData/evileye_test.db",
        "images_dir": "EvilEyeData/images",
        "preview_height": 200,
        "preview_width": 200
    },
    "database_adapters": {
        "DatabaseAdapterObjects": {
            "table_name": "objects"
        },
        "DatabaseAdapterCamEvents": {
            "table_name": "camera_events",
            "event_name": "CameraEvent"
        },
        "DatabaseAdapterFieldOfViewEvents": {
            "table_name": "fov_events",
            "event_name": "FieldOfViewEvent"
        },
        "DatabaseAdapterZoneEvents": {
            "table_name": "zone_events",
            "event_name": "ZoneEvent"
        }
    }
}
```

### 2. **Создан `credentials.json`**

Содержит чувствительные данные:

```json
{
  "sources" : {
    "rtsp://name": {
      "username": "user",
      "password": "password"
    }
  },
  "database": {
    "user_name": "evileye_user",
    "password": "evileye_password",
    "database_name": "/home/user/EvilEye/EvilEyeData/evileye_test.db",
    "host_name": "localhost",
    "port": 5432,
    "admin_user_name": "postgres",
    "admin_password": ""
  }
}
```

## 🏗️ Принципы архитектуры

### Разделение ответственности:

1. **`credentials.json`** (не в git):
   - ✅ Пароли и токены
   - ✅ Пользовательские данные
   - ✅ Чувствительная информация

2. **`database_config.json`** (в git):
   - ✅ Техническая конфигурация
   - ✅ Структура адаптеров
   - ✅ Настройки производительности

3. **Основная конфигурация** (в git):
   - ✅ Бизнес-логика
   - ✅ Может переопределить любые настройки
   - ✅ Специфичные для проекта настройки

### Приоритет загрузки:

1. **Значения по умолчанию** (hardcoded в коде)
2. **`credentials.json`** (переопределяет defaults)
3. **`database_config.json`** (переопределяет credentials)
4. **Основная конфигурация** (переопределяет все)

## 🔒 Безопасность

### Правила для credentials:

- ✅ **`credentials.json` в .gitignore** - не попадает в репозиторий
- ✅ **`credentials_proto.json` в git** - шаблон для разработчиков
- ✅ **Чувствительные данные** только в credentials.json
- ✅ **Техническая конфигурация** в database_config.json

## 🚀 Результат

### Теперь система работает правильно:

1. **Загружается `credentials.json`** с чувствительными данными
2. **Загружается `database_config.json`** с технической конфигурацией
3. **Credentials переопределяют** значения по умолчанию
4. **Database_config переопределяет** credentials
5. **Основная конфигурация** может переопределить все

### Проверка:

При запуске EvilEye:
- ✅ **Credentials загружаются** из credentials.json
- ✅ **Database config загружается** из database_config.json
- ✅ **База данных инициализируется** с правильными параметрами
- ✅ **Configuration History доступна**

## 📋 Рекомендации

### Для разработки:
- **Используйте `credentials_proto.json`** как шаблон
- **Создайте `credentials.json`** на основе прототипа
- **Не добавляйте credentials** в database_config.json

### Для production:
- **Настройте `credentials.json`** под вашу инфраструктуру
- **Используйте переменные окружения** для чувствительных данных
- **Регулярно обновляйте** пароли и токены

## 🎉 Заключение

Исправление восстановило правильную архитектуру credentials EvilEye:

- ✅ **Credentials отделены** от технической конфигурации
- ✅ **Безопасность обеспечена** - чувствительные данные не в git
- ✅ **Гибкость сохранена** - можно переопределить любые настройки
- ✅ **Архитектура соответствует** принципам проекта

**Система готова к использованию с правильной архитектурой credentials!** 🚀
