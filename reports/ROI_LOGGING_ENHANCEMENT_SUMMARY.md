# Улучшение логирования информации о выбранном ROI

## 🎯 **Запрос пользователя**
Добавить в лог информацию о толщине линии и цвете выбранного ROI после строк:
```
2025-10-12 18:50:25,292 - INFO - ROI state updated: selected_id = 2
2025-10-12 18:50:25,309 - INFO - Mouse released at scene position: PyQt6.QtCore.QPointF(2252.199413489736, 1593.431085043988)
```

## ✅ **Реализованные изменения**

### **1. Добавлен метод `_log_selected_roi_info()`**
```python
def _log_selected_roi_info(self, roi_id):
    """Логировать информацию о выбранном ROI"""
    if 0 <= roi_id < len(self.rois):
        roi_item = self.rois[roi_id]
        roi_data = self.roi_data[roi_id]
        
        # Получаем информацию о пере
        pen = roi_item.pen()
        pen_color = pen.color()
        pen_width = pen.width()
        
        # Получаем оригинальный цвет из данных
        original_color = roi_data.get("color", (255, 0, 0))
        
        self.logger.info(f"Selected ROI info: ID={roi_id}, pen_color=RGB({pen_color.red()},{pen_color.green()},{pen_color.blue()}), pen_width={pen_width}, original_color={original_color}")
```

### **2. Модифицирован метод `set_roi_state()`**
```python
def set_roi_state(self, **kwargs):
    """Установить состояние ROI"""
    for key, value in kwargs.items():
        if key in self.roi_state:
            self.roi_state[key] = value
            self.logger.info(f"ROI state updated: {key} = {value}")
            
            # Если обновляется selected_id, логируем дополнительную информацию
            if key == 'selected_id' and value >= 0:
                self._log_selected_roi_info(value)
```

### **3. Модифицирован метод `mouseReleaseEvent()`**
```python
def mouseReleaseEvent(self, event):
    """Обработка отпускания мыши"""
    scene_pos = self.mapToScene(event.pos())
    self.logger.info(f"Mouse released at scene position: {scene_pos}")
    
    # ... обработка событий ...
    
    # Логируем информацию о выбранном ROI после отпускания мыши
    selected_id = self.get_selected_roi_id()
    if selected_id >= 0:
        self._log_selected_roi_info(selected_id)
```

## 📝 **Новый формат логов**

### **Теперь в логах будет:**

#### **1. При обновлении состояния ROI:**
```
2025-10-12 18:50:25,292 - INFO - ROI state updated: selected_id = 2
2025-10-12 18:50:25,293 - INFO - Selected ROI info: ID=2, pen_color=RGB(255,100,100), pen_width=8, original_color=(255, 0, 0)
```

#### **2. При отпускании мыши:**
```
2025-10-12 18:50:25,309 - INFO - Mouse released at scene position: PyQt6.QtCore.QPointF(2252.199413489736, 1593.431085043988)
2025-10-12 18:50:25,310 - INFO - Selected ROI info: ID=2, pen_color=RGB(255,100,100), pen_width=8, original_color=(255, 0, 0)
```

## 🎨 **Информация в логах**

### **Формат:**
```
Selected ROI info: ID={roi_id}, pen_color=RGB({r},{g},{b}), pen_width={width}, original_color={color}
```

### **Параметры:**
- **`ID`** - идентификатор выбранного ROI
- **`pen_color`** - цвет пера в формате RGB (цвет выделения)
- **`pen_width`** - толщина пера в пикселях
- **`original_color`** - оригинальный цвет ROI

### **Примеры значений:**

#### **Цвета пера (pen_color):**
- `RGB(255,100,100)` - ярко-красный (цвет выделения)
- `RGB(255,0,0)` - красный (обычный цвет)
- `RGB(0,255,0)` - зеленый (обычный цвет)
- `RGB(0,0,255)` - синий (обычный цвет)

#### **Толщина пера (pen_width):**
- `4` - обычная толщина
- `8` - толщина выделения (4 × 2.0 множитель)
- `6` - промежуточная толщина (при масштабировании)

#### **Оригинальные цвета (original_color):**
- `(255, 0, 0)` - красный
- `(0, 255, 0)` - зеленый
- `(0, 0, 255)` - синий
- `(255, 255, 0)` - желтый
- `(255, 0, 255)` - фиолетовый

## 🧪 **Тестирование**

### **Создан тест `test_roi_logging.py` с 4 тестами:**

1. **`test_log_selected_roi_info`** - проверяет логирование информации о ROI
2. **`test_set_roi_state_logging`** - проверяет логирование при обновлении состояния
3. **`test_mouse_release_logging`** - проверяет логирование при отпускании мыши
4. **`test_logging_format_explanation`** - объясняет формат логирования

### **Результаты тестов:**
```
Ran 4 tests in 0.540s
OK
```

## 🎯 **Когда логируется информация**

### **1. При выборе ROI:**
- Пользователь кликает на ROI
- Вызывается `_select_roi()`
- Вызывается `set_roi_state(selected_id=X)`
- Логируется: `ROI state updated: selected_id = X`
- Логируется: `Selected ROI info: ID=X, ...`

### **2. При отпускании мыши:**
- Пользователь отпускает кнопку мыши
- Вызывается `mouseReleaseEvent()`
- Логируется: `Mouse released at scene position: ...`
- Логируется: `Selected ROI info: ID=X, ...`

### **3. При изменении размера ROI:**
- Пользователь перетаскивает маркеры изменения размера
- Вызывается `_update_roi_size()`
- Вызывается `set_roi_state(selected_id=X)`
- Логируется: `ROI state updated: selected_id = X`
- Логируется: `Selected ROI info: ID=X, ...`

## 🎉 **Результат**

### **Теперь в логах будет полная информация:**
- ✅ ID выбранного ROI
- ✅ Цвет пера (RGB)
- ✅ Толщина пера
- ✅ Оригинальный цвет ROI

### **Это поможет:**
- 🔍 Отлаживать проблемы с выделением ROI
- 🎨 Проверять правильность цветов и толщины
- 📊 Анализировать поведение пользователя
- 🐛 Находить ошибки в логике выделения

## 🚀 **Итог**

Добавлено подробное логирование информации о выбранном ROI, включая толщину линии и цвет. Теперь разработчики и пользователи смогут видеть полную информацию о состоянии ROI в логах!
