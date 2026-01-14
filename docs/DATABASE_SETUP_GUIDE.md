# Руководство по настройке базы данных для EvilEye

## 🎯 Проблема

При запуске EvilEye вы видите предупреждение:
```
WARNING - Database enabled but unavailable. Working without database. Reason: 'image_dir'
```

Это означает, что система пытается использовать базу данных, но не может найти необходимые параметры конфигурации.

## ✅ Решение

### 1. **База данных уже добавлена в конфигурацию**

В файл `configs/poly-cameras.json` была добавлена секция `database`:

```json
"database": {
    "type": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database_name": "evilEye",
    "user_name": "evileye_user",
    "password": "evileye_password",
    "images_dir": "EvilEyeData/images",
    "preview_height": 200,
    "preview_width": 200
}
```

### 2. **Создана директория для изображений**

Директория `EvilEyeData/images` создана для хранения изображений.

## 🚀 Варианты настройки

### Вариант 1: Использовать существующую PostgreSQL базу данных

Если у вас уже есть PostgreSQL сервер:

1. **Создайте базу данных:**
```sql
CREATE DATABASE evileye;
CREATE USER evileye_user WITH PASSWORD 'evileye_password';
GRANT ALL PRIVILEGES ON DATABASE evileye TO evileye_user;
```

2. **Обновите параметры подключения** в `configs/poly-cameras.json`:
```json
"database": {
    "type": "postgresql",
    "host": "your_postgres_host",
    "port": 5432,
    "database_name": "evileye",
    "user_name": "your_username",
    "password": "your_password",
    "images_dir": "EvilEyeData/images",
    "preview_height": 200,
    "preview_width": 200
}
```

### Вариант 2: Отключить базу данных (работать в JSON режиме)

Если вы не хотите использовать базу данных:

1. **Удалите или закомментируйте секцию `database`** в конфигурации
2. **Система автоматически переключится** на JSON режим журнала
3. **Configuration History будет недоступна**, но основная функциональность будет работать

### Вариант 3: Использовать SQLite (упрощенный вариант)

Для тестирования можно использовать SQLite:

```json
"database": {
    "type": "sqlite",
    "database_name": "evileye.db",
    "images_dir": "EvilEyeData/images",
    "preview_height": 200,
    "preview_width": 200
}
```

## 🔧 Проверка настройки

### После настройки базы данных:

1. **Перезапустите EvilEye**
2. **Проверьте логи** - не должно быть предупреждений о недоступности БД
3. **Кнопка Configuration History** должна стать активной в главном окне
4. **В окне Settings** должны быть доступны функции истории

### Признаки успешной настройки:

```
INFO - Database connection established
INFO - ConfigHistoryManager initialized
INFO - Configuration History available
```

## 📋 Функциональность с базой данных

### С включенной базой данных доступно:
- ✅ **Автоматическое сохранение** конфигураций при запуске
- ✅ **Просмотр истории** всех запущенных конфигураций
- ✅ **Восстановление конфигураций** из истории
- ✅ **Сравнение конфигураций** между собой
- ✅ **Экспорт истории** в JSON файлы
- ✅ **Фильтрация по дате** и другим параметрам

### Без базы данных (JSON режим):
- ✅ **Основная функциональность** EvilEye работает
- ✅ **Сохранение в JSON файлы** (если настроено)
- ❌ **Configuration History недоступна**
- ❌ **Автоматическое сохранение конфигураций** не работает

## 🎉 Рекомендации

### Для разработки и тестирования:
- **Используйте SQLite** - проще в настройке
- **Создайте тестовую базу** с минимальными правами

### Для production:
- **Используйте PostgreSQL** - более надежно и производительно
- **Настройте резервное копирование** базы данных
- **Используйте отдельного пользователя** с ограниченными правами

## 🔍 Устранение проблем

### Проблема: "Database enabled but unavailable"
**Решение:** Проверьте параметры подключения в секции `database`

### Проблема: "Connection refused"
**Решение:** Убедитесь, что PostgreSQL сервер запущен и доступен

### Проблема: "Authentication failed"
**Решение:** Проверьте имя пользователя и пароль в конфигурации

### Проблема: "Database does not exist"
**Решение:** Создайте базу данных и пользователя согласно инструкции выше

---

**После настройки базы данных система истории конфигураций EvilEye будет полностью функциональна!** 🚀
