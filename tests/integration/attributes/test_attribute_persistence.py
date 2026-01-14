#!/usr/bin/env python3
"""
Тест персистентности состояний атрибутов
"""

import time
from evileye.objects_handler.attribute_manager import AttributeManager
from evileye.objects_handler.object_result import ObjectResult

def test_attribute_persistence():
    """Тест сохранения состояний атрибутов"""
    print("=== Тест персистентности атрибутов ===")
    
    # Создаем AttributeManager
    attr_manager = AttributeManager(
        thresholds_conf={'hard_hat': 0.5},
        thresholds_time={'hard_hat': {'min_time_ms': 30, 'confirm_time_ms': 60}},
        ema_alpha=0.7
    )
    
    # Создаем объект
    obj = ObjectResult()
    obj.track = type('Track', (), {'track_id': 123})()
    
    print("\n--- Шаг 1: Первая детекция атрибута ---")
    now_ts = time.time()
    attr_manager.update(123, 'hard_hat', True, 0.8, now_ts, 50)  # 50ms детекции
    
    # Получаем состояния
    states = attr_manager.get_states(123)
    print(f"Состояния: {[(name, state.state, state.confidence_smooth, state.total_time_ms) for name, state in states.items()]}")
    
    # Сохраняем в объект
    obj.attributes = {k: vars(v) for k, v in states.items()}
    print(f"Атрибуты в объекте: {obj.attributes}")
    
    print("\n--- Шаг 2: Продолжаем детекцию ---")
    attr_manager.update(123, 'hard_hat', True, 0.9, now_ts + 0.1, 100)  # еще 100ms
    
    states = attr_manager.get_states(123)
    print(f"Состояния: {[(name, state.state, state.confidence_smooth, state.total_time_ms) for name, state in states.items()]}")
    
    # Сохраняем в объект
    obj.attributes = {k: vars(v) for k, v in states.items()}
    print(f"Атрибуты в объекте: {obj.attributes}")
    
    print("\n--- Шаг 3: Потеря детекции на один кадр ---")
    attr_manager.update(123, 'hard_hat', False, 0.0, now_ts + 0.2, 33)  # 33ms без детекции
    
    states = attr_manager.get_states(123)
    print(f"Состояния: {[(name, state.state, state.confidence_smooth, state.total_time_ms) for name, state in states.items()]}")
    
    # Сохраняем в объект
    obj.attributes = {k: vars(v) for k, v in states.items()}
    print(f"Атрибуты в объекте: {obj.attributes}")
    
    print("\n--- Шаг 4: Возобновление детекции ---")
    attr_manager.update(123, 'hard_hat', True, 0.85, now_ts + 0.3, 50)  # снова детекция
    
    states = attr_manager.get_states(123)
    print(f"Состояния: {[(name, state.state, state.confidence_smooth, state.total_time_ms) for name, state in states.items()]}")
    
    # Сохраняем в объект
    obj.attributes = {k: vars(v) for k, v in states.items()}
    print(f"Атрибуты в объекте: {obj.attributes}")
    
    print("\n--- Проблема: _ensure_all_attributes_present ---")
    # Симулируем вызов _ensure_all_attributes_present
    configured_attrs = ['hard_hat', 'no_hard_hat']
    
    # Добавляем недостающие атрибуты с 'none' состоянием
    for attr_name in configured_attrs:
        if attr_name not in obj.attributes:
            obj.attributes[attr_name] = {
                'attr_name': attr_name,
                'state': 'none',
                'confidence_smooth': 0.0,
                'frames_present': 0,
                'total_time_ms': 0,
                'no_detect_time_ms': 0,
                'enter_count': 0,
                'enter_ts': None,
                'last_seen_ts': None,
                'ema_alpha': 0.7
            }
    
    print(f"Атрибуты после _ensure_all_attributes_present: {obj.attributes}")
    print("❌ ПРОБЛЕМА: Существующие атрибуты могут быть перезаписаны!")

if __name__ == "__main__":
    test_attribute_persistence()


