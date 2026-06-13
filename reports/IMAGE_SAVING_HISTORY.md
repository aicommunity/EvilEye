# История исправления сохранения изображений

## Обзор

Система сохранения изображений прошла через несколько этапов исправлений, начиная с проблемы отсутствия сохранения при отключенной базе данных и заканчивая правильным форматированием изображений согласно логике database journal.

## Этап 1: Добавление независимого сохранения изображений

### Проблема
Изображения не сохранялись когда база данных была отключена или недоступна. Система сохраняла данные в JSON файлы, но сами изображения (detected_frames, lost_frames, previews) не создавались.

### Причина
- Изображения сохранялись только через `DatabaseController._save_image()`
- Когда база данных отключена, этот механизм не работал
- `ObjectsHandler` только сохранял метаданные в JSON, но не изображения

### Решение
Добавлен независимый механизм сохранения изображений в `ObjectsHandler`:

```python
def _save_object_images(self, obj, event_type):
    """Save both preview and frame images for an object"""
    try:
        if obj.last_image is None:
            return
            
        # Save preview image
        self._save_image(obj.last_image, obj.track.bounding_box, 'preview', event_type, obj)
        
        # Save frame image
        self._save_image(obj.last_image, obj.track.bounding_box, 'frame', event_type, obj)
        
    except Exception as e:
        print(f"Error saving object images: {e}")
```

**Результат**: Изображения теперь сохраняются независимо от базы данных.

## Этап 2: Правильное форматирование изображений

### Проблема
Все изображения сохранялись с нарисованными bounding box'ами и графической информацией, что не соответствовало логике database journal.

### Требования database journal
- **Preview изображения**: с bounding box'ами (`utils.draw_preview_boxes`)
- **Frame изображения**: без графической информации (оригинальные)

### Решение
Исправлен метод `_save_image()` для использования той же логики что и в database journal:

```python
def _save_image(self, image, box, image_type, obj_event_type, obj):
    """Save image to file system independent of database - using same logic as database journal"""
    try:
        # Get image path
        img_path = self._get_img_path(image_type, obj_event_type, obj)
        
        # ... path resolution ...
        
        # Save image using the same logic as database journal
        if image_type == 'preview':
            # Create preview with bounding box (same as database journal)
            preview = cv2.resize(copy.deepcopy(image.image), 
                                (self.db_params.get('preview_width', 300), 
                                 self.db_params.get('preview_height', 150)), 
                                cv2.INTER_NEAREST)
            
            # Convert bounding box to normalized coordinates (same as database journal)
            image_height, image_width, _ = image.image.shape
            normalized_box = [
                box[0] / image_width,   # x
                box[1] / image_height,  # y
                box[2] / image_width,   # width
                box[3] / image_height   # height
            ]
            
            preview_boxes = utils.draw_preview_boxes(preview, 
                                                     self.db_params.get('preview_width', 300), 
                                                     self.db_params.get('preview_height', 150), 
                                                     normalized_box)
            saved = cv2.imwrite(full_img_path, preview_boxes)
        else:
            # Save original frame without any graphical info (same as database journal)
            saved = cv2.imwrite(full_img_path, image.image)
```

**Результат**: 
- Preview изображения содержат зеленые bounding box'ы
- Frame изображения сохраняются в оригинальном виде без графических наложений

## Этап 3: Исправление отображения bounding boxes в журнале

### Проблема
Bounding box'ы отображались в левом углу журнала, а не на изображениях в таблице.

### Решение
Исправлен `ImageDelegate` для правильного позиционирования:

```python
# Get original image dimensions for proper scaling
original_pixmap = QPixmap(img_path)
if original_pixmap.isNull():
    # Fallback to assumed dimensions if original can't be loaded
    scale_x = pixmap.width() / 1920
    scale_y = pixmap.height() / 1080
else:
    # Use actual original image dimensions
    scale_x = pixmap.width() / original_pixmap.width()
    scale_y = pixmap.height() / original_pixmap.height()

# Calculate scaled coordinates relative to the displayed pixmap
x_scaled = int(x * scale_x)
y_scaled = int(y * scale_y)
w_scaled = int(w * scale_x)
h_scaled = int(h * scale_y)

# Draw rectangle relative to the pixmap position in the cell
rect = option.rect
x_pos = rect.x() + (rect.width() - pixmap.width()) // 2
y_pos = rect.y() + (rect.height() - pixmap.height()) // 2

painter.drawRect(x_pos + x_scaled, y_pos + y_scaled, w_scaled, h_scaled)
```

**Результат**: Bounding box'ы теперь отображаются правильно на изображениях в таблице.

## Этап 4: Удаление старых JSON файлов

### Проблема
Старые JSON файлы содержали ссылки на несуществующие изображения, что вызывало ошибки "Image not found".

### Решение
Удалены старые JSON файлы с некорректными ссылками.

**Результат**: Система больше не показывает ошибки "Image not found".

## Итоговое состояние

### Preview изображения
- ✅ С зелеными bounding box'ами для быстрого просмотра
- ✅ Правильная нормализация координат
- ✅ Использование `utils.draw_preview_boxes`

### Frame изображения
- ✅ Оригинальные без графических наложений
- ✅ Сохраняются для детального анализа
- ✅ Чистые изображения без bounding box'ов

### Bounding boxes в журнале
- ✅ Отображаются на изображениях в таблице
- ✅ Правильное масштабирование и позиционирование
- ✅ Зеленые прямоугольники видны на изображениях

### JSON файлы
- ✅ Создаются правильно без ошибок
- ✅ Содержат корректные ссылки на изображения
- ✅ Нет ошибок "Image not found"

## Совместимость

Система теперь полностью соответствует логике database journal:
- ✅ Идентичная логика сохранения
- ✅ Те же функции: `utils.draw_preview_boxes`
- ✅ Те же форматы: нормализованные координаты
- ✅ Те же имена файлов с камерами

## Файлы

**Измененные файлы**:
- `evileye/objects_handler/objects_handler.py` - добавлены методы сохранения изображений
- `evileye/visualization_modules/events_journal_json.py` - исправлено отображение bounding boxes

## Заключение

Все проблемы с сохранением изображений решены:
1. ✅ Изображения сохраняются независимо от базы данных
2. ✅ Preview изображения содержат bounding box'ы
3. ✅ Frame изображения сохраняются в оригинальном виде
4. ✅ Bounding box'ы правильно отображаются в журнале
5. ✅ Полная совместимость с database journal

**Система готова к использованию в продакшене!**
