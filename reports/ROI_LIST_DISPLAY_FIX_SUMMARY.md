# Исправление отображения ROI в списке

## 🎯 **Проблема**
Пользователи могут видеть и модифицировать ROI в редакторе, но ROI не отображаются в списке справа.

## 🔍 **Причина**
В методе `add_roi_direct()` в файле `roi_core.py` отсутствовала проверка флага `_loading_from_config`, что приводило к неправильному поведению при загрузке ROI из конфигурации.

### **Проблемные места:**
1. **Отсутствие проверки флага**: `add_roi_direct()` всегда испускал сигнал `roi_added`
2. **Отсутствие синхронизации данных**: `add_roi_direct()` не добавлял данные в `roi_data`

## ✅ **Исправления**

### **1. Добавлена проверка флага в `add_roi_direct()`**
```python
def add_roi_direct(self, coords: List[int], color: Tuple[int, int, int] = (255, 0, 0)):
    roi_item = self._create_roi_item(coords, color)
    if roi_item:
        self.rois.append(roi_item)
        self.roi_data.append({"coords": coords, "color": color})  # ← ДОБАВЛЕНО!
        self.scene.update()
        # Испускаем сигнал для обновления списка (только если это не загрузка из конфига)
        if not hasattr(self, '_loading_from_config') or not self._loading_from_config:  # ← ДОБАВЛЕНО!
            self.roi_added.emit(coords)
        return roi_item
    return None
```

### **2. Исправлена синхронизация данных**
- Добавлено `self.roi_data.append({"coords": coords, "color": color})` в `add_roi_direct()`
- Теперь `roi_data` и `rois` всегда синхронизированы

## 🔄 **Поток работы после исправления**

### **При загрузке из конфига:**
```
set_rois_from_config()
    ↓
_loading_from_config = True
    ↓
add_roi_direct() (БЕЗ сигнала)
    ↓
_loading_from_config = False
    ↓
_update_roi_list() (один раз в конце)
    ↓
Список обновляется корректно!
```

### **При рисовании нового ROI:**
```
Пользователь рисует ROI
    ↓
_finish_drawing()
    ↓
add_roi() (ВСЕГДА испускает сигнал)
    ↓
roi_added.emit(coords)
    ↓
_on_roi_added(coords)
    ↓
_update_roi_list()
    ↓
Список обновляется немедленно!
```

## 🧪 **Тестирование**

### **Создан новый тест `test_roi_list_fix.py` с 4 тестами:**

1. **`test_add_roi_direct_without_loading_flag`** - проверяет, что сигнал испускается без флага загрузки
2. **`test_add_roi_direct_with_loading_flag`** - проверяет, что сигнал НЕ испускается с флагом загрузки
3. **`test_add_roi_always_emits_signal`** - проверяет, что `add_roi` всегда испускает сигнал
4. **`test_roi_data_synchronization`** - проверяет синхронизацию `roi_data` и `rois`

### **Результаты тестов:**
```
Ran 4 tests in 0.412s
OK
```

## 🎉 **Результат**

### **До исправления:**
- ❌ ROI не отображались в списке при загрузке из конфига
- ❌ Неправильная синхронизация данных
- ❌ Множественные обновления списка

### **После исправления:**
- ✅ ROI корректно отображаются в списке
- ✅ Правильная синхронизация `roi_data` и `rois`
- ✅ Оптимизированные обновления списка
- ✅ Корректная работа при загрузке из конфига
- ✅ Мгновенное обновление при рисовании

## 🔧 **Технические детали**

### **Ключевые изменения:**
1. **Условное испускание сигнала** в `add_roi_direct()`
2. **Синхронизация данных** между `rois` и `roi_data`
3. **Проверка флага** `_loading_from_config`

### **Файлы изменены:**
- `evileye/visualization_modules/roi_core.py` - основное исправление
- `test_roi_list_fix.py` - новый тест
- `test_roi_list_update.py` - обновлен импорт

## 🚀 **Итог**

Проблема с отображением ROI в списке полностью решена! Теперь пользователи будут видеть все ROI в списке справа, независимо от того, как они были созданы (рисование или загрузка из конфига).

