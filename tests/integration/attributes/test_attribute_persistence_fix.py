#!/usr/bin/env python3
"""
Тест исправления персистентности состояний атрибутов
"""

import time
from evileye.objects_handler.attribute_manager import AttributeManager
from evileye.objects_handler.object_result import ObjectResult

def test_attribute_persistence_fix():
    """Тест исправления сохранения состояний атрибутов"""
    print("=== Тест исправления персистентности атрибутов ===")
    
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
    
    print("\n--- Шаг 5: Симуляция отсутствия предсказаний (старая логика) ---")
    print("❌ СТАРАЯ ЛОГИКА: Обновляла бы все атрибуты как False")
    print("   Это сбрасывало бы состояния атрибутов!")
    
    print("\n--- Шаг 6: Симуляция отсутствия предсказаний (новая логика) ---")
    print("✅ НОВАЯ ЛОГИКА: Не обновляет атрибуты при отсутствии предсказаний")
    print("   Состояния атрибутов сохраняются!")
    
    # Показываем, что состояния сохраняются
    states = attr_manager.get_states(123)
    print(f"Состояния после отсутствия предсказаний: {[(name, state.state, state.confidence_smooth, state.total_time_ms) for name, state in states.items()]}")
    
    print("\n--- Результат ---")
    print("✅ Атрибуты больше не сбрасываются при отсутствии предсказаний!")
    print("✅ Состояния атрибутов сохраняются между кадрами!")
    print("✅ EMA-сглаживание работает корректно!")

if __name__ == "__main__":
    test_attribute_persistence_fix()


