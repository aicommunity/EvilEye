# Добавление команды `evileye deploy`

## Обзор

Добавлена новая команда `evileye deploy` в CLI интерфейс для быстрого развертывания базовых конфигурационных файлов.

## Изменения

### Добавленная функциональность

**Команда `evileye deploy`:**
- ✅ Копирует `credentials_proto.json` в `credentials.json` (если не существует)
- ✅ Создает папку `configs` (если не существует)
- ✅ Безопасная работа - не перезаписывает существующие файлы
- ✅ Информативные сообщения о процессе выполнения

### Обновленные файлы

#### 1. `evileye/cli.py`
- ✅ Добавлена функция `deploy()`
- ✅ Интеграция с Typer CLI framework
- ✅ Обработка ошибок и информативные сообщения

#### 2. `README.md`
- ✅ Обновлен раздел "Basic Usage"
- ✅ Добавлен новый раздел "CLI Commands"
- ✅ Добавлен пример полного рабочего процесса

#### 3. `CLI_DEPLOY_COMMAND.md`
- ✅ Создана подробная документация команды
- ✅ Примеры использования
- ✅ Описание безопасности и обработки ошибок

## Тестирование

### ✅ Успешно протестировано:

1. **Команда в списке:**
   ```bash
   evileye --help
   # deploy         Deploy EvilEye configuration files to current directory.
   ```

2. **Помощь команды:**
   ```bash
   evileye deploy --help
   # Показывает описание и параметры
   ```

3. **Развертывание в новой директории:**
   ```bash
   mkdir /tmp/test_deploy
   cd /tmp/test_deploy
   evileye deploy
   # ✓ Copied credentials_proto.json to credentials.json
   # ✓ Created configs folder
   ```

4. **Повторный запуск (безопасность):**
   ```bash
   evileye deploy
   # credentials.json already exists, skipping...
   # configs folder already exists, skipping...
   ```

5. **Интеграция с create:**
   ```bash
   evileye-create test_config --sources 2
   # ✅ Configuration created successfully!
   ```

## Рабочий процесс

### Полный цикл использования:

1. **Развертывание:**
   ```bash
   evileye deploy
   ```

2. **Создание конфигурации:**
   ```bash
   evileye-create my_config --sources 2 --source-type ip_camera
   ```

3. **Запуск системы:**
   ```bash
   evileye run configs/my_config.json
   ```

## Преимущества

1. **Упрощение настройки:** Один шаг для подготовки рабочей директории
2. **Безопасность:** Не перезаписывает существующие файлы
3. **Информативность:** Понятные сообщения о процессе
4. **Интеграция:** Работает с существующими командами
5. **Документация:** Полная документация и примеры

## Результат

**Команда `evileye deploy` успешно добавлена и протестирована!**

Пользователи теперь могут быстро развертывать EvilEye в любой директории с помощью одной команды.



