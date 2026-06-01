# Перемещение database_config.json в пакет

## Обзор

Файл `database_config.json` был перемещен из корневой директории проекта в пакет `evileye/` для лучшей организации кода.

## Изменения

### Перемещение файла
```bash
mv database_config.json evileye/
```

### Обновленные файлы

#### 1. `evileye/controller/controller.py`
- **Добавлен импорт:** `import os`
- **Обновлен путь к файлу:**
  ```python
  # Было:
  with open("database_config.json") as data_config_file:
  
  # Стало:
  with open(os.path.join(os.path.dirname(__file__), "..", "database_config.json")) as data_config_file:
  ```

#### 2. `evileye/controller/async_controller.py`
- **Обновлен путь к файлу:**
  ```python
  # Было:
  with open("database_config.json", 'r') as data_config_file:
  
  # Стало:
  with open(os.path.join(os.path.dirname(__file__), "..", "database_config.json"), 'r') as data_config_file:
  ```

#### 3. `evileye/visualization_modules/configurer/configurer_window.py`
- **Обновлены пути к файлу:**
  ```python
  # Было:
  with open("database_config.json", 'r+') as database_config_file:
  with open("database_config.json") as data_config_file:
  
  # Стало:
  with open(os.path.join(utils.get_project_root(), "evileye", "database_config.json"), 'r+') as database_config_file:
  with open(os.path.join(utils.get_project_root(), "evileye", "database_config.json")) as data_config_file:
  ```

## Преимущества

1. **Лучшая организация:** Конфигурационные файлы теперь находятся внутри пакета
2. **Изоляция:** Файлы проекта отделены от пользовательских конфигураций
3. **Совместимость:** Все существующие функции продолжают работать
4. **Упаковка:** Файл будет включен в пакет при установке

## Тестирование

✅ **evileye-create** - работает корректно
✅ **evileye-process** - работает корректно
✅ **evileye** - работает корректно

## Структура файла

Файл `evileye/database_config.json` содержит:
- Схему таблиц базы данных
- Конфигурацию адаптеров базы данных
- Настройки изображений и превью
- Параметры подключения к базе данных

## Результат

**Файл `database_config.json` успешно перемещен в пакет `evileye/` и все ссылки обновлены!**



