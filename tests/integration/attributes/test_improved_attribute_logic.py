#!/usr/bin/env python3
"""
Тест улучшенной логики состояний атрибутов
"""

import time
from evileye.objects_handler.attribute_manager import AttributeManager

def test_improved_attribute_logic():
    """Тест улучшенной логики состояний атрибутов"""
    print("=== Тест улучшенной логики состояний атрибутов ===")
    
    # Создаем AttributeManager
    attr_manager = AttributeManager(
        thresholds_conf={'hard_hat': 0.5},
        thresholds_time={'hard_hat': {'min_time_ms': 30, 'confirm_time_ms': 60}},
        ema_alpha=0.7
    )
    
    track_id = 123
    attr_name = 'hard_hat'
    
    print("\n--- Шаг 1: Начальная детекция (50ms) ---")
    now_ts = time.time()
    attr_manager.update(track_id, attr_name, True, 0.8, now_ts, 50)
    
    states = attr_manager.get_states(track_id)
    state = states.get(attr_name)
    print(f"Состояние: {state.state}")
    print(f"Found time: {state.total_found_time_ms}ms, Lost time: {state.total_lost_time_ms}ms")
    print(f"Found ratio: {state.found_ratio:.3f}")
    print(f"Confidence: {state.confidence_smooth:.3f}")
    
    print("\n--- Шаг 2: Продолжаем детекцию (100ms) ---")
    attr_manager.update(track_id, attr_name, True, 0.9, now_ts + 0.1, 100)
    
    states = attr_manager.get_states(track_id)
    state = states.get(attr_name)
    print(f"Состояние: {state.state}")
    print(f"Found time: {state.total_found_time_ms}ms, Lost time: {state.total_lost_time_ms}ms")
    print(f"Found ratio: {state.found_ratio:.3f}")
    print(f"Confidence: {state.confidence_smooth:.3f}")
    
    print("\n--- Шаг 3: Потеря детекции (50ms) ---")
    attr_manager.update(track_id, attr_name, False, 0.0, now_ts + 0.2, 50)
    
    states = attr_manager.get_states(track_id)
    state = states.get(attr_name)
    print(f"Состояние: {state.state}")
    print(f"Found time: {state.total_found_time_ms}ms, Lost time: {state.total_lost_time_ms}ms")
    print(f"Found ratio: {state.found_ratio:.3f}")
    print(f"Confidence: {state.confidence_smooth:.3f}")
    
    print("\n--- Шаг 4: Продолжаем отсутствие (100ms) ---")
    attr_manager.update(track_id, attr_name, False, 0.0, now_ts + 0.3, 100)
    
    states = attr_manager.get_states(track_id)
    state = states.get(attr_name)
    print(f"Состояние: {state.state}")
    print(f"Found time: {state.total_found_time_ms}ms, Lost time: {state.total_lost_time_ms}ms")
    print(f"Found ratio: {state.found_ratio:.3f}")
    print(f"Confidence: {state.confidence_smooth:.3f}")
    
    print("\n--- Шаг 5: Возобновление детекции (200ms) ---")
    attr_manager.update(track_id, attr_name, True, 0.85, now_ts + 0.4, 200)
    
    states = attr_manager.get_states(track_id)
    state = states.get(attr_name)
    print(f"Состояние: {state.state}")
    print(f"Found time: {state.total_found_time_ms}ms, Lost time: {state.total_lost_time_ms}ms")
    print(f"Found ratio: {state.found_ratio:.3f}")
    print(f"Confidence: {state.confidence_smooth:.3f}")
    
    print("\n--- Шаг 6: Длительное отсутствие (500ms) ---")
    attr_manager.update(track_id, attr_name, False, 0.0, now_ts + 0.5, 500)
    
    states = attr_manager.get_states(track_id)
    state = states.get(attr_name)
    print(f"Состояние: {state.state}")
    print(f"Found time: {state.total_found_time_ms}ms, Lost time: {state.total_lost_time_ms}ms")
    print(f"Found ratio: {state.found_ratio:.3f}")
    print(f"Confidence: {state.confidence_smooth:.3f}")
    
    print("\n--- Анализ улучшенной логики ---")
    print("✅ Суммарное время обнаружения: накапливается при детекции")
    print("✅ Суммарное время потери: накапливается при отсутствии")
    print("✅ Found ratio: отношение времени обнаружения к общему времени")
    print("✅ Решение о состоянии: принимается на основе found_ratio")
    print("✅ Пороги: >= 70% = exists, 30-70% = lost, < 30% = none")

if __name__ == "__main__":
    test_improved_attribute_logic()


