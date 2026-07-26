# Исторические отчеты EvilEye

Эта папка содержит исторические отчеты о разработке, исправлениях и изменениях системы EvilEye. Отчеты были объединены и организованы по темам для лучшей навигации и понимания истории развития проекта.

## 📚 Объединенные отчеты

### Основные темы

#### 🔧 ROI Editor
- **[ROI_EDITOR_HISTORY.md](ROI_EDITOR_HISTORY.md)** - Полная история развития ROI Editor: от диалога до независимого окна, исправления зависания, улучшения интерфейса

#### 🖱️ Double Click
- **[DOUBLE_CLICK_FIX_HISTORY.md](DOUBLE_CLICK_FIX_HISTORY.md)** - История исправления проблемы с двойным кликом в Events Journal через три итерации

#### 💾 Сохранение изображений
- **[IMAGE_SAVING_HISTORY.md](IMAGE_SAVING_HISTORY.md)** - История исправления сохранения изображений: от независимого сохранения до правильного форматирования

#### 📋 Events Journal
- **[JOURNAL_HISTORY.md](JOURNAL_HISTORY.md)** - История развития Events Journal: от базовой функциональности до полной совместимости с database journal

#### ⚙️ История конфигураций
- **[CONFIG_HISTORY_HISTORY.md](CONFIG_HISTORY_HISTORY.md)** - История реализации системы истории конфигураций: просмотр, восстановление, сравнение

#### 🏷️ Параметр classes
- **[CLASSES_PARAMETER_HISTORY.md](CLASSES_PARAMETER_HISTORY.md)** - История исправления параметра classes: решение проблемы с асинхронной загрузкой моделей

#### 🔨 Другие исправления
- **[OTHER_FIXES_HISTORY.md](OTHER_FIXES_HISTORY.md)** - Различные исправления и улучшения: GUI, база данных, атрибуты, очистка кода

#### 🌿 Ветки vs develop (autorefactor)
- **[BRANCH_DEVELOP_INDEX.md](BRANCH_DEVELOP_INDEX.md)** — итоговый отчёт и ссылки на сравнение веток `autorefactor_capture`, `autorefactor_preprocessor`, `autorefactor_db`, `autorefactor_tracking`, `autorefactor_detection` с `develop`

## 📁 Исходные отчеты

Исходные отчеты сохранены в этой папке для справки. Они были использованы для создания объединенных документов выше.

### Категории исходных отчетов

#### ROI Editor (32 файла)
- Исправления зависания: `ROI_EDITOR_FREEZE_*`, `ROI_LOADING_FREEZE_*`
- Конвертация диалога: `ROI_DIALOG_TO_WINDOW_*`, `ROI_DIALOG_REMOVAL_*`
- Различные исправления: `ROI_*_FIX_*`, `ROI_*_SUMMARY.md`

#### Journal (12 файлов)
- Основные отчеты: `JOURNAL_FINAL_REPORT.md`, `JOURNAL_FIXES_SUMMARY.md`
- Обновления: `JOURNAL_UPDATES_*`, `JOURNAL_COLUMNS_*`
- Исправления: `JOURNAL_*_FIX_*`

#### Double Click (3 файла)
- `DOUBLE_CLICK_FIX_REPORT.md`
- `DOUBLE_CLICK_FINAL_FIX_REPORT.md`
- `FINAL_DOUBLE_CLICK_FIX_REPORT.md`

#### Image Saving (4 файла)
- `IMAGE_SAVING_FIX_REPORT.md`
- `CORRECT_IMAGE_SAVING_FINAL_REPORT.md`
- `FINAL_IMAGE_SAVING_SUCCESS_REPORT.md`
- `IMAGE_FIXES_FINAL_REPORT.md`

#### Config History (6 файлов)
- `CONFIG_HISTORY_IMPLEMENTATION_SUMMARY.md`
- `CONFIG_HISTORY_FINAL_SUMMARY.md`
- `CONFIG_HISTORY_SUCCESS_SUMMARY.md`
- `CONFIG_HISTORY_UPDATE_SUMMARY.md`
- `config-history-architecture.md`
- `config-history-architecture-updated.md`

#### Classes Parameter (2 файла)
- `CLASSES_PARAMETER_FIX.md`
- `CLASSES_PARAMETER_FIX_V2.md`

#### GUI (6 файлов)
- `GUI_FINAL_FIXES.md`
- `GUI_FIX_SUMMARY.md`
- `GUI_IMPORT_FIXES.md`
- `GUI_UPDATE_SUMMARY.md`
- `GUI_ATTRIBUTE_DISPLAY_UPDATE.md`

#### Database (5 файлов)
- `DATABASE_ISSUE_RESOLUTION.md`
- `DATABASE_CONFIG_FIX.md`
- `DATABASE_CONFIG_MOVE.md`
- `DATABASE_OPTION_README.md`
- `CREDENTIALS_ARCHITECTURE_FIX.md`

#### Attributes (6 файлов)
- `ATTRIBUTE_CODE_CLEANUP.md`
- `ATTRIBUTE_PERSISTENCE_FIX.md`
- `ATTRIBUTE_STATE_TRANSITIONS_FIX.md`
- `ATTRIBUTES_GUI_EXPLANATION.md`
- `ATTRIBUTES_SAMPLE_CONFIG.md`
- `IMPROVED_ATTRIBUTE_LOGIC.md`

#### Classes & Mapping (5 файлов)
- `CENTRALIZED_CLASS_SYSTEM.md`
- `CLASS_MAPPING_UPDATE.md`
- `AUTO_CLASS_MAPPING_UPDATE.md`

#### Pipeline (3 файла)
- `PIPELINE_BASE_METHODS_SUMMARY.md`
- `PIPELINE_CLASS_INIT_FEATURE.md`
- `PIPELINE_GENERATOR_FEATURE.md`

#### Jobs History (3 файла)
- `JOBS_HISTORY_FINAL_FIX.md`
- `JOBS_HISTORY_JSON_DISPLAY_FIX.md`
- `JOBS_HISTORY_SQL_FIX.md`

#### Deploy (2 файла)
- `DEPLOY_COMMAND_SUMMARY.md`
- `DEPLOY_SAMPLES_COMMAND.md`

#### Other (1 файл)
- `PROJECT_COMPLETION_SUMMARY.md`
- `INDEX_FIX_SUMMARY.md`

## 📊 Статистика

- **Всего исторических отчетов**: ~80 файлов
- **Объединенных документов**: 7 файлов
- **Исходных отчетов**: ~73 файла (сохранены для справки)
- **Удалено устаревших отчетов**: 14 файлов (завершенные миграции, неактуальные попытки, выполненные планы)

## 🎯 Как использовать

### Для понимания истории изменений
1. Начните с **объединенных отчетов** - они содержат полную историю по каждой теме
2. При необходимости обратитесь к **исходным отчетам** для деталей

### Для поиска конкретной информации
1. Используйте **объединенные отчеты** для быстрого обзора
2. Ищите по ключевым словам в **исходных отчетах** для деталей

## 📝 Примечание

Эти документы сохраняются для исторической справки. Для актуальной документации см. [docs/](../docs/).

Объединенные отчеты были созданы для:
- Устранения дублирования информации
- Улучшения понимания истории изменений
- Упрощения навигации по историческим данным
- Сохранения всех деталей в структурированном виде
