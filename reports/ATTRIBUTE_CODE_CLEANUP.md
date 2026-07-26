# Очистка неиспользуемого кода атрибутов

## Проблема

Пользователь обнаружил, что в строке 455 `pred` всегда `None`, `_attr_pending` всегда пустой, и `put_attributes` никогда не вызывается. Но атрибуты все равно вычисляются и показываются в GUI.

## Анализ потока данных

### ✅ Реальный поток данных атрибутов

```
AttributeClassifier → tracking_data.attr_results → ObjectsHandler
```

1. **AttributeClassifier._classify_roi_with_detector()**
   - Обрабатывает ROI изображения
   - Возвращает результаты атрибутов
   - Сохраняет в `tracking_data.attr_results[track_id]`

2. **ObjectsHandler._handle_active()**
   - Строка 444: `if hasattr(tracking_results, 'attr_results')`
   - Строка 449: `attr_manager.update(track_id, attr_name, detected_now, confidence, now_ts, dt_ms)`

### ❌ Неиспользуемый код

1. **`_attr_pending: dict[int, dict[str, float]] = {}`**
   - Инициализируется в `__init__`
   - Заполняется в `put_attributes()`
   - НО `put_attributes()` НИКОГДА НЕ ВЫЗЫВАЕТСЯ
   - `pred` в строке 455 всегда `None`

2. **`put_attributes()` метод**
   - Определен в `ObjectsHandler`
   - НО нигде не вызывается
   - Атрибуты приходят через `tracking_results.attr_results`

3. **Логика с `_attr_pending`**
   - `pred = self._attr_pending.pop(getattr(obj.track, 'track_id', None), None)`
   - `if pred:` блок в `_handle_active`
   - Всегда `None`, никогда не выполняется

## Удаленный код

### 1. Удалена инициализация `_attr_pending`

```python
# ❌ УДАЛЕНО
self._attr_pending: dict[int, dict[str, float]] = {}
```

### 2. Удален метод `put_attributes()`

```python
# ❌ УДАЛЕНО
def put_attributes(self, track_id: int, attrs: dict[str, float]):
    """Публичный метод приёма результатов атрибутов для конкретного трека.
    attrs: {attr_name: confidence}
    """
    if track_id is None or not attrs:
        return
    self._attr_pending[track_id] = attrs
```

### 3. Удалена неиспользуемая логика с `_attr_pending`

```python
# ❌ УДАЛЕНО
# Применяем накопленные предсказания к объектам текущего source
for obj in self.active_objs.objects:
    if obj.source_id != tracking_results.source_id:
        continue
    pred = self._attr_pending.pop(getattr(obj.track, 'track_id', None), None)
    if pred:
        for attr_name, conf in pred.items():
            self.attr_manager.update(obj.track.track_id, attr_name, True, float(conf), now_ts, dt_ms)
    # Не обновляем атрибуты как False, если нет предсказаний - это может сбросить состояния
    # Сохранить снимок состояний в объект
    attr_states = self.attr_manager.get_states(obj.track.track_id)
    obj.attributes = {k: vars(v) for k, v in attr_states.items()}
    
    # Убедиться, что все настроенные атрибуты присутствуют в объекте
    if self._is_primary_object(obj):
        self._ensure_all_attributes_present(obj)
```

### 4. Упрощена логика сохранения состояний

```python
# ✅ НОВАЯ УПРОЩЕННАЯ ЛОГИКА
# Сохранить снимок состояний атрибутов в объекты
for obj in self.active_objs.objects:
    if obj.source_id != tracking_results.source_id:
        continue
        
    # Сохранить снимок состояний в объект
    attr_states = self.attr_manager.get_states(obj.track.track_id)
    obj.attributes = {k: vars(v) for k, v in attr_states.items()}
    
    # Убедиться, что все настроенные атрибуты присутствуют в объекте
    if self._is_primary_object(obj):
        self._ensure_all_attributes_present(obj)
```

## Результаты очистки

### ✅ Преимущества

1. **Упрощение кода**: Удален неиспользуемый код
2. **Ясность**: Поток данных стал понятнее
3. **Производительность**: Меньше ненужных операций
4. **Поддержка**: Код стал проще для понимания

### 📊 Статистика удаления

- **Удалено строк кода**: ~15
- **Удалено методов**: 1 (`put_attributes`)
- **Удалено переменных**: 1 (`_attr_pending`)
- **Упрощено логики**: 1 (обработка атрибутов)

### 🔍 Что осталось работать

- ✅ `tracking_results.attr_results` обработка
- ✅ `attr_manager.update()` вызовы
- ✅ `obj.attributes` сохранение
- ✅ `_ensure_all_attributes_present()` метод

## Архитектурная ясность

### Реальный поток данных

```
1. AttributeClassifier обрабатывает ROI
2. Сохраняет результаты в tracking_data.attr_results[track_id]
3. tracking_data передается через пайплайн
4. ObjectsHandler получает tracking_results.attr_results
5. Обновляет AttributeManager
6. Сохраняет снимок состояний в obj.attributes
7. GUI отображает obj.attributes
```

### Удаленные компоненты

- ❌ `_attr_pending` - неиспользуемый буфер
- ❌ `put_attributes()` - неиспользуемый метод
- ❌ Логика с `pred` - неиспользуемая обработка

## Заключение

Очистка неиспользуемого кода атрибутов:

- ✅ **Упростила код**: Удален мертвый код
- ✅ **Улучшила ясность**: Поток данных стал понятнее
- ✅ **Сохранила функциональность**: Атрибуты работают как прежде
- ✅ **Повысила производительность**: Меньше ненужных операций

**Система атрибутов стала чище и понятнее, сохранив всю функциональность!** 🎉


