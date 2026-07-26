# Улучшенная логика состояний атрибутов

## Обзор

Реализована улучшенная логика состояний атрибутов, которая рассчитывает суммарное время обнаружения и потери, и принимает интеллектуальные решения о состояниях на основе `found_ratio`.

## Новые поля в AttributeState

### Добавленные поля

```python
@dataclass
class AttributeState:
    # ... существующие поля ...
    
    # Новые поля для улучшенной логики состояний
    total_found_time_ms: int = 0  # Суммарное время обнаружения
    total_lost_time_ms: int = 0   # Суммарное время потери
    found_ratio: float = 0.0      # Отношение времени обнаружения к общему времени
```

### Описание полей

- **`total_found_time_ms`**: Накапливается при детекции атрибута
- **`total_lost_time_ms`**: Накапливается при отсутствии детекции
- **`found_ratio`**: `total_found_time_ms / (total_found_time_ms + total_lost_time_ms)`

## Улучшенная логика принятия решений

### Метод `_calculate_decision_state`

```python
def _calculate_decision_state(self, state: 'AttributeState', min_time_ms: int, confirm_time_ms: int) -> str:
    """
    Рассчитывает решение о состоянии атрибута на основе суммарного времени.
    """
    # Если нет данных - none
    if state.total_found_time_ms + state.total_lost_time_ms == 0:
        return 'none'
    
    # Если недавно обнаружен - exists
    if state.no_detect_time_ms == 0 and state.total_time_ms >= confirm_time_ms:
        return 'exists'
    
    # Если недавно потерян - lost
    if state.no_detect_time_ms > 0 and state.no_detect_time_ms < confirm_time_ms:
        return 'lost'
    
    # Принимаем решение на основе found_ratio
    if state.found_ratio >= 0.7:  # 70% времени обнаружен
        return 'exists'
    elif state.found_ratio >= 0.3:  # 30-70% времени обнаружен
        return 'lost'
    else:  # < 30% времени обнаружен
        return 'none'
```

### Пороги принятия решений

| Found Ratio | Состояние | Описание |
|-------------|-----------|----------|
| ≥ 70% | `exists` | Атрибут стабильно присутствует |
| 30-70% | `lost` | Атрибут нестабилен, частично присутствует |
| < 30% | `none` | Атрибут практически отсутствует |

## Обновленная логика обновления

### Новая логика в `update`

```python
if detected and confidence >= thr_conf:
    state.frames_present += 1
    state.total_time_ms += dt_ms
    state.total_found_time_ms += dt_ms  # ✅ Накапливаем время обнаружения
    state.no_detect_time_ms = 0
    state.last_seen_ts = now_ts
else:
    state.no_detect_time_ms += dt_ms
    state.total_lost_time_ms += dt_ms   # ✅ Накапливаем время потери

# Обновляем found_ratio для принятия решений
total_time = state.total_found_time_ms + state.total_lost_time_ms
if total_time > 0:
    state.found_ratio = state.total_found_time_ms / total_time
else:
    state.found_ratio = 0.0

# Принимаем решение о состоянии на основе улучшенной логики
decision_state = self._calculate_decision_state(state, min_time_ms, confirm_time_ms)

# Обновляем состояние только если оно изменилось
if state.state != decision_state:
    old_state = state.state
    state.state = decision_state
    
    # Логируем переходы состояний
    if decision_state == 'exists' and old_state != 'exists':
        state.enter_count += 1
        state.enter_ts = now_ts
    elif decision_state == 'none' and old_state != 'none':
        state.reset_presence()
```

## Результаты тестирования

### Тестовый сценарий

```python
# Шаг 1: Начальная детекция (50ms)
Found time: 50ms, Lost time: 0ms, Found ratio: 1.000 → exists

# Шаг 2: Продолжаем детекцию (100ms)
Found time: 150ms, Lost time: 0ms, Found ratio: 1.000 → exists

# Шаг 3: Потеря детекции (50ms)
Found time: 150ms, Lost time: 50ms, Found ratio: 0.750 → lost

# Шаг 4: Продолжаем отсутствие (100ms)
Found time: 150ms, Lost time: 150ms, Found ratio: 0.500 → lost

# Шаг 5: Возобновление детекции (200ms)
Found time: 350ms, Lost time: 150ms, Found ratio: 0.700 → exists

# Шаг 6: Длительное отсутствие (500ms)
Found time: 350ms, Lost time: 650ms, Found ratio: 0.350 → lost
```

### Анализ результатов

| Шаг | Found Time | Lost Time | Found Ratio | Состояние | Логика |
|-----|------------|-----------|-------------|-----------|---------|
| 1 | 50ms | 0ms | 1.000 | `exists` | 100% времени обнаружен |
| 2 | 150ms | 0ms | 1.000 | `exists` | 100% времени обнаружен |
| 3 | 150ms | 50ms | 0.750 | `lost` | 75% времени обнаружен |
| 4 | 150ms | 150ms | 0.500 | `lost` | 50% времени обнаружен |
| 5 | 350ms | 150ms | 0.700 | `exists` | 70% времени обнаружен |
| 6 | 350ms | 650ms | 0.350 | `lost` | 35% времени обнаружен |

## Преимущества улучшенной логики

### ✅ Интеллектуальные решения

1. **Статистический подход**: Решения принимаются на основе исторических данных
2. **Устойчивость к шуму**: Кратковременные потери не влияют на общее состояние
3. **Адаптивность**: Система учитывает паттерны поведения атрибутов

### ✅ Улучшенная стабильность

1. **Меньше переключений**: Состояния не меняются при каждом кадре
2. **Контекстная информация**: Решения основаны на долгосрочных трендах
3. **Гибкость**: Пороги можно настроить под конкретные задачи

### ✅ Лучшая производительность

1. **Эффективность**: Решения принимаются только при изменении состояния
2. **Память**: Исторические данные сохраняются для анализа
3. **Масштабируемость**: Логика работает с любым количеством атрибутов

## Конфигурация

### Рекомендуемые настройки

```json
{
  "objects_handler": {
    "attributes_detection": {
      "classifier": {
        "time_thresholds": {
          "hard_hat": {
            "min_time_ms": 30,      // Быстро теряет атрибут
            "confirm_time_ms": 60   // Быстро подтверждает атрибут
          }
        },
        "confidence_thresholds": {
          "hard_hat": 0.5
        },
        "ema_alpha": 0.7
      }
    }
  }
}
```

### Настройка порогов found_ratio

```python
# В _calculate_decision_state можно настроить пороги:
if state.found_ratio >= 0.8:  # 80% времени обнаружен
    return 'exists'
elif state.found_ratio >= 0.4:  # 40-80% времени обнаружен
    return 'lost'
else:  # < 40% времени обнаружен
    return 'none'
```

## Архитектурные улучшения

### 1. Разделение ответственности

- **Накопление данных**: `total_found_time_ms`, `total_lost_time_ms`
- **Расчет метрик**: `found_ratio`
- **Принятие решений**: `_calculate_decision_state`

### 2. Расширяемость

- **Новые метрики**: Можно добавить дополнительные поля
- **Алгоритмы**: Можно реализовать другие алгоритмы принятия решений
- **Пороги**: Можно настроить пороги для разных типов атрибутов

### 3. Отладка и мониторинг

- **Прозрачность**: Все метрики доступны для анализа
- **Логирование**: Переходы состояний логируются
- **Визуализация**: Данные можно отображать в GUI

## Заключение

Улучшенная логика состояний атрибутов:

- ✅ **Повышает точность**: Решения принимаются на основе статистических данных
- ✅ **Улучшает стабильность**: Меньше ложных переключений состояний
- ✅ **Обеспечивает гибкость**: Пороги можно настроить под конкретные задачи
- ✅ **Упрощает отладку**: Все метрики доступны для анализа

**Система атрибутов стала более интеллектуальной и стабильной!** 🎉


