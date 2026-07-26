# Исправление отображения ROI окна

## 🎯 **Проблема**
ROI окно не зависает, но отображается внутри главного окна и неправильно отрисовывается.

## 🔍 **Анализ проблемы**

### **Основные причины:**
1. **Неправильное родительское окно** - ROI окно было установлено как дочернее окно главного окна
2. **Неправильные флаги окна** - ROI окно не было настроено как независимое окно
3. **Проблемы с отрисовкой** - canvas не обновлялся правильно
4. **Отсутствие импорта Qt** - не был импортирован Qt для установки флагов окна

## ✅ **Комплексные исправления**

### **1. Исправлено родительское окно**
```python
# БЫЛО:
self.roi_editor_window.setParent(self)

# СТАЛО:
# Убираем родительское окно для независимого отображения
self.roi_editor_window.setParent(None)
# Устанавливаем как независимое окно
self.roi_editor_window.setWindowFlags(self.roi_editor_window.windowFlags() | Qt.WindowType.Window)
```

### **2. Добавлены правильные флаги окна в конструктор**
```python
# В ROIEditorWindow.__init__()
# Устанавливаем флаги для независимого окна
self.setWindowFlags(Qt.WindowType.Window)
self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
```

### **3. Добавлен импорт Qt**
```python
# Добавлен импорт Qt в ROIEditorWindow
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
# или для PyQt5
from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
```

### **4. Улучшена отрисовка canvas**
```python
# Принудительно обновляем canvas
self.roi_canvas.scene.update()
self.roi_canvas.update()
self.roi_canvas.repaint()
# Принудительно обновляем все окно
self.update()
self.repaint()
```

### **5. Добавлено принудительное отображение окна**
```python
# Проверяем, что окно действительно видимо
if self.roi_editor_window.isVisible():
    self.logger.info("ROI Editor window is visible")
    # Принудительно показываем окно
    self.roi_editor_window.show()
    self.roi_editor_window.raise_()
    self.roi_editor_window.activateWindow()
else:
    self.logger.warning("ROI Editor window is not visible")
    # Пытаемся принудительно показать
    self.roi_editor_window.show()
    self.roi_editor_window.raise_()
    self.roi_editor_window.activateWindow()
```

## 🧪 **Тестирование**

### **Создан тест `test_roi_window_display.py` с 5 тестами:**

1. **`test_roi_window_independence`** - проверяет независимость ROI окна
2. **`test_roi_window_visibility`** - проверяет видимость ROI окна
3. **`test_roi_window_size_and_position`** - проверяет размер и позицию
4. **`test_roi_window_with_image`** - проверяет работу с изображением
5. **`test_roi_window_with_roi`** - проверяет работу с ROI

### **Результаты тестов:**
```
Ran 5 tests in 0.655s
OK
```

## 🎉 **Результат**

### **До исправления:**
- ❌ ROI окно отображалось внутри главного окна
- ❌ Неправильная отрисовка
- ❌ Отсутствие независимости окна
- ❌ Проблемы с видимостью

### **После исправления:**
- ✅ ROI окно отображается как независимое окно
- ✅ Правильная отрисовка canvas
- ✅ Корректные флаги окна
- ✅ Принудительное обновление отображения
- ✅ Все тесты проходят успешно

## 🔧 **Технические детали**

### **Ключевые изменения:**
1. **Убрано родительское окно** - `setParent(None)`
2. **Добавлены правильные флаги** - `Qt.WindowType.Window`
3. **Добавлен импорт Qt** для работы с флагами
4. **Улучшена отрисовка** - добавлены `repaint()` и `update()`
5. **Добавлено принудительное отображение** окна

### **Файлы изменены:**
- `evileye/visualization_modules/roi_editor_window.py` - добавлены флаги окна и импорт Qt
- `evileye/visualization_modules/main_window.py` - исправлено родительское окно
- `test_roi_window_display.py` - создан тест для проверки отображения

## 🚀 **Итог**

Проблема с отображением ROI окна полностью решена! Теперь ROI окно:
- Отображается как независимое окно
- Правильно отрисовывается
- Имеет корректные флаги и атрибуты
- Проходит все тесты

