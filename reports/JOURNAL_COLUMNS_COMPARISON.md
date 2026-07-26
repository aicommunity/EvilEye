# Journal Columns Comparison

## Database Objects Journal vs JSON Objects Journal

### 📊 **Database Objects Journal** (`handler_journal_view.py`)

**Колонки (7 колонок):**
1. **Name** - `source_name` (имя камеры)
2. **Event** - `'Event'` (фиксированное значение)
3. **Information** - `'Object Id=' || object_id || '; class: ' || class_id || '; conf: ' || ROUND(confidence::numeric, 2)`
4. **Time** - `time_stamp` (время обнаружения)
5. **Time lost** - `time_lost` (время потери)
6. **Preview** - `preview_path` (путь к preview изображению)
7. **Lost preview** - `lost_preview_path` (путь к lost preview изображению)

**SQL Query:**
```sql
SELECT source_name, CAST('Event' AS text) AS event_type, 
       'Object Id=' || object_id || '; class: ' || class_id || '; conf: ' || ROUND(confidence::numeric, 2) AS information,
       time_stamp, time_lost, preview_path, lost_preview_path 
FROM objects 
WHERE time_stamp BETWEEN :start AND :finish
```

### 📄 **JSON Objects Journal** (`events_journal_json.py`)

**Колонки (6 колонок):**
1. **Event** - `"Object {object_id}"` (номер объекта)
2. **Time** - `ts` (время обнаружения)
3. **Time lost** - `ts` (время потери)
4. **Information** - `"Object Id={object_id}; class: {class_name}; conf: {confidence:.2f}"`
5. **Preview** - `image_filename` (путь к preview изображению)
6. **Lost preview** - `image_filename` (путь к lost preview изображению)

**Данные из JSON:**
```python
row_data = {
    'event': f"Object {object_id}",
    'time': found_event.get('ts') if found_event else (lost_event.get('ts') if lost_event else ''),
    'time_lost': lost_event.get('ts') if lost_event else '',
    'information': f"Object Id={object_id}; class: {base_event.get('class_name', base_event.get('class_id', ''))}; conf: {base_event.get('confidence', 0):.2f}",
    'preview': found_event.get('image_filename') if found_event else '',
    'lost_preview': lost_event.get('image_filename') if lost_event else ''
}
```

## 🔍 **Основные различия:**

### 1. **Количество колонок:**
- **Database**: 7 колонок
- **JSON**: 6 колонок

### 2. **Отсутствующая колонка в JSON:**
- **Database**: имеет колонку **"Name"** (source_name камеры)
- **JSON**: НЕТ колонки с именем камеры

### 3. **Различия в колонке "Event":**
- **Database**: фиксированное значение `'Event'`
- **JSON**: динамическое значение `"Object {object_id}"`

### 4. **Различия в колонке "Information":**
- **Database**: `'Object Id=' || object_id || '; class: ' || class_id || '; conf: ' || ROUND(confidence::numeric, 2)`
- **JSON**: `"Object Id={object_id}; class: {class_name}; conf: {confidence:.2f}"`

### 5. **Источники данных:**
- **Database**: данные из PostgreSQL базы данных
- **JSON**: данные из JSON файлов (`objects_found.json`, `objects_lost.json`)

## 🎯 **Рекомендации по унификации:**

### ✅ **Вариант 1: Добавить колонку "Name" в JSON journal**
```python
# Добавить в row_data:
'name': base_event.get('source_name', 'Unknown'),
```

### ✅ **Вариант 2: Убрать колонку "Name" из Database journal**
```sql
-- Убрать source_name из SELECT
SELECT CAST('Event' AS text) AS event_type, 
       'Object Id=' || object_id || '; class: ' || class_id || '; conf: ' || ROUND(confidence::numeric, 2) AS information,
       time_stamp, time_lost, preview_path, lost_preview_path 
FROM objects 
WHERE time_stamp BETWEEN :start AND :finish
```

### ✅ **Вариант 3: Унифицировать формат "Event"**
- **Database**: изменить на `"Object {object_id}"`
- **JSON**: оставить как есть

## 📋 **Текущее состояние:**

| Колонка | Database | JSON | Статус |
|---------|----------|------|--------|
| Name | ✅ | ❌ | **Различие** |
| Event | 'Event' | 'Object {id}' | **Различие** |
| Information | SQL формат | JSON формат | **Различие** |
| Time | ✅ | ✅ | **Одинаково** |
| Time lost | ✅ | ✅ | **Одинаково** |
| Preview | ✅ | ✅ | **Одинаково** |
| Lost preview | ✅ | ✅ | **Одинаково** |

## 🔧 **Предлагаемые изменения:**

1. **Добавить колонку "Name" в JSON journal** для полной совместимости
2. **Унифицировать формат "Event"** для консистентности
3. **Стандартизировать формат "Information"** для единообразия

**Какой вариант предпочтительнее?**

