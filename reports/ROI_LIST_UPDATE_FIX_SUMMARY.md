# Исправление обновления списка ROI при рисовании

## 🎯 **Проблема**
Когда пользователь рисует новый ROI, список ROI не обновляется немедленно.

## 🔍 **Причина**
В методе `add_roi()` не испускался сигнал `roi_added`, поэтому обработчик `_on_roi_added()` не вызывался, и список не обновлялся.

## ✅ **Исправления**

### **1. Добавлен сигнал в метод `add_roi()`**
```python
def add_roi(self, coords: List[int], color: Tuple[int, int, int] = (255, 0, 0)):
    # ... создание ROI ...
    
    # Принудительно обновляем сцену
    self.scene.update()
    
    # Испускаем сигнал для обновления списка
    self.roi_added.emit(coords)  # ← ДОБАВЛЕНО!
    
    return roi_item
```

### **2. Добавлен условный сигнал в метод `add_roi_direct()`**
```python
def add_roi_direct(self, coords: List[int], color: Tuple[int, int, int] = (255, 0, 0)):
    # ... создание ROI ...
    
    # Испускаем сигнал для обновления списка (только если это не загрузка из конфига)
    if not hasattr(self, '_loading_from_config') or not self._loading_from_config:
        self.roi_added.emit(coords)  # ← ДОБАВЛЕНО!
    
    return roi_item
```

### **3. Добавлен флаг для предотвращения множественных обновлений**
```python
def set_rois_from_config(self, params, source_id):
    # ... загрузка ROI ...
    
    # Устанавливаем флаг загрузки из конфига
    self.roi_canvas._loading_from_config = True
    
    # Добавляем ROI из конфигурации
    for i, roi_data in enumerate(rois_data):
        self.roi_canvas.add_roi_direct(coords, color)
    
    # Сбрасываем флаг загрузки из конфига
    self.roi_canvas._loading_from_config = False
    
    # Обновляем список ROI один раз в конце
    self._update_roi_list()
```

## 🔄 **Поток обновления списка**

### **При рисовании нового ROI:**
```
Пользователь рисует ROI
    ↓
_finish_drawing()
    ↓
add_roi(coords, color)
    ↓
roi_added.emit(coords)  ← НОВЫЙ СИГНАЛ!
    ↓
_on_roi_added(coords)
    ↓
_update_roi_list()
    ↓
Список обновляется немедленно!
```

### **При загрузке из конфига:**
```
set_rois_from_config()
    ↓
_loading_from_config = True
    ↓
add_roi_direct() (без сигнала)
    ↓
_loading_from_config = False
    ↓
_update_roi_list() (один раз в конце)
    ↓
Список обновляется один раз!
```

## 🧪 **Тестирование**

### **Создан тест `test_roi_list_update.py` с 4 тестами:**

1. **`test_roi_added_signal_emission`** - проверяет испускание сигнала при добавлении ROI
2. **`test_roi_added_signal_not_emitted_during_config_loading`** - проверяет, что сигнал не испускается при загрузке из конфига
3. **`test_roi_added_signal_emitted_after_config_loading`** - проверяет, что сигнал испускается после загрузки из конфига
4. **`test_roi_list_update_flow`** - проверяет полный поток обновления списка

### **Результаты тестов:**
```
Ran 4 tests in 0.390s
OK
```

## 🎉 **Результат**

### **До исправления:**
- ❌ Список ROI не обновлялся при рисовании
- ❌ Пользователь не видел новый ROI в списке
- ❌ Нужно было перезагружать окно

### **После исправления:**
- ✅ Список ROI обновляется немедленно
- ✅ Пользователь видит новый ROI в списке сразу
- ✅ ROI выделен и готов к редактированию
- ✅ Нет множественных обновлений при загрузке из конфига

## 🔧 **Технические детали**

### **Сигналы PyQt6:**
- `roi_added = pyqtSignal(list)` - сигнал при добавлении ROI
- `roi_removed = pyqtSignal(int)` - сигнал при удалении ROI
- `roi_updated = pyqtSignal(int, list)` - сигнал при обновлении ROI

### **Обработчики сигналов:**
- `_on_roi_added(coords)` - обновляет список при добавлении
- `_on_roi_removed(index)` - обновляет список при удалении
- `_on_roi_updated(index, coords)` - обновляет список при изменении

### **Флаг `_loading_from_config`:**
- Предотвращает множественные обновления списка при загрузке из конфига
- Устанавливается в `True` в начале загрузки
- Сбрасывается в `False` в конце загрузки
- Используется в `add_roi_direct()` для условного испускания сигнала

## 🚀 **Итог**

Проблема с обновлением списка ROI при рисовании полностью решена! Теперь пользователи будут видеть новые ROI в списке немедленно после их создания.
