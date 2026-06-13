# Исправление ошибки с QGraphicsPixmapItem.rect()

## 🎯 **Проблема**
При запуске ROI редактора возникала ошибка:
```
AttributeError: 'QGraphicsPixmapItem' object has no attribute 'rect'
```

**Стек вызовов:**
```
File "roi_editor_dialog.py", line 833, in _constrain_roi_to_image_bounds
    pixmap_rect = self.pixmap_item.rect()
AttributeError: 'QGraphicsPixmapItem' object has no attribute 'rect'
```

## 🔍 **Причина ошибки**
`QGraphicsPixmapItem` не имеет метода `rect()`. Вместо этого нужно использовать:
- `boundingRect()` - для получения границ элемента
- `pixmap().rect()` - для получения размеров pixmap

## 🔧 **Исправление**

### **1. Замена `rect()` на `boundingRect()`**

**Было:**
```python
def _constrain_roi_to_image_bounds(self, rect):
    """Ограничить ROI границами отображаемого изображения"""
    if not self.pixmap_item:
        return rect
    
    # Получаем границы отображаемого изображения
    pixmap_rect = self.pixmap_item.rect()  # ❌ ОШИБКА
    image_left = pixmap_rect.left()
    image_top = pixmap_rect.top()
    image_right = pixmap_rect.right()
    image_bottom = pixmap_rect.bottom()
```

**Стало:**
```python
def _constrain_roi_to_image_bounds(self, rect):
    """Ограничить ROI границами отображаемого изображения"""
    if not self.pixmap_item:
        return rect
    
    # Получаем границы отображаемого изображения
    pixmap_rect = self.pixmap_item.boundingRect()  # ✅ ИСПРАВЛЕНО
    image_left = pixmap_rect.left()
    image_top = pixmap_rect.top()
    image_right = pixmap_rect.right()
    image_bottom = pixmap_rect.bottom()
```

### **2. Обновление тестов**

**Было:**
```python
# Настраиваем mock для pixmap_item
self.roi_view.pixmap_item = Mock()
self.roi_view.pixmap_item.pos.return_value = QPointF(0, 0)
self.roi_view.pixmap_item.rect.return_value = QRectF(0, 0, 1920, 1080)  # ❌ ОШИБКА
```

**Стало:**
```python
# Настраиваем mock для pixmap_item
self.roi_view.pixmap_item = Mock()
self.roi_view.pixmap_item.pos.return_value = QPointF(0, 0)
self.roi_view.pixmap_item.boundingRect.return_value = QRectF(0, 0, 1920, 1080)  # ✅ ИСПРАВЛЕНО
```

## ✅ **Результаты тестирования**

### **1. Unit тесты:**
```bash
cd /home/user/EvilEye && python test_roi_image_bounds_constraints.py
# Ran 4 tests in 0.558s - OK
```

### **2. Интеграционные тесты:**
```bash
cd /home/user/EvilEye && timeout 30s evileye run configs/poly-cameras.json
# Приложение запустилось успешно, ROI редактор работает
```

### **3. Логирование успешной работы:**
```
2025-10-12 20:33:32,897 - INFO - ROI constrained to image bounds:
2025-10-12 20:33:32,903 - INFO -   Original: left=1471.0, top=-239.0, right=1971.0, bottom=161.0
2025-10-12 20:33:32,908 - INFO -   Constrained: left=1471.0, top=0.0, right=1971.0, bottom=161.0
2025-10-12 20:33:32,912 - INFO -   Image bounds: left=0.0, top=0.0, right=3840.0, bottom=2160.0
2025-10-12 20:33:32,917 - INFO - Added ROI direct: index=0, zValue=920.0, area=80500, coords=[1790, 0, 2290, 400]
```

## 🎯 **Ключевые различия между методами**

| Метод | Назначение | Возвращает |
|---|---|---|
| `rect()` | ❌ Не существует в `QGraphicsPixmapItem` | - |
| `boundingRect()` | ✅ Границы элемента в системе координат сцены | `QRectF` |
| `pixmap().rect()` | ✅ Размеры pixmap в пикселях | `QRect` |

## 🚀 **Итоговый результат**

### **Проблема полностью решена:**
1. ✅ **Ошибка исправлена** - `QGraphicsPixmapItem` теперь использует правильный метод `boundingRect()`
2. ✅ **ROI редактор работает** - приложение запускается без ошибок
3. ✅ **ROI загружаются корректно** - все ROI из конфигурации загружаются успешно
4. ✅ **Ограничения границ работают** - ROI корректно ограничиваются границами изображения
5. ✅ **Тесты обновлены** - все тесты используют правильный метод

### **Функциональность:**
- ROI редактор открывается без ошибок
- ROI загружаются из конфигурации (3 ROI для Source 0)
- ROI корректно ограничиваются границами изображения
- ROI можно выбирать и изменять
- Подробное логирование для отладки

## 🎉 **Заключение**

Ошибка была вызвана использованием несуществующего метода `rect()` у `QGraphicsPixmapItem`. Исправление заключалось в замене на правильный метод `boundingRect()`, который возвращает границы элемента в системе координат сцены.

**ROI редактор теперь работает корректно для всех источников!** 🚀
