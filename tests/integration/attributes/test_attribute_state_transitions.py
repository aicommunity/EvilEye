#!/usr/bin/env python3
"""
Тест переходов состояний атрибутов
"""

import time
from evileye.objects_handler.attribute_manager import AttributeManager

def test_attribute_state_transitions():
    """Тест переходов состояний атрибутов"""
    print("=== Тест переходов состояний атрибутов ===")
    
    # Создаем AttributeManager с текущими настройками
    attr_manager = AttributeManager(
        thresholds_conf={'hard_hat': 0.5},
        thresholds_time={'hard_hat': {'min_time_ms': 30, 'confirm_time_ms': 60}},
        ema_alpha=1.0  # Как в конфигурации
    )
    
    track_id = 123
    attr_name = 'hard_hat'
    
    print("\n--- Шаг 1: Первая детекция атрибута ---")
    now_ts = time.time()
    attr_manager.update(track_id, attr_name, True, 0.8, now_ts, 50)  # 50ms детекции
    
    states = attr_manager.get_states(track_id)
    state = states.get(attr_name)
    print(f"Состояние: {state.state}, confidence: {state.confidence_smooth:.3f}, total_time: {state.total_time_ms}ms, no_detect: {state.no_detect_time_ms}ms")
    
    print("\n--- Шаг 2: Продолжаем детекцию ---")
    attr_manager.update(track_id, attr_name, True, 0.9, now_ts + 0.1, 100)  # еще 100ms
    
    states = attr_manager.get_states(track_id)
    state = states.get(attr_name)
    print(f"Состояние: {state.state}, confidence: {state.confidence_smooth:.3f}, total_time: {state.total_time_ms}ms, no_detect: {state.no_detect_time_ms}ms")
    
    print("\n--- Шаг 3: Потеря детекции ---")
    attr_manager.update(track_id, attr_name, False, 0.0, now_ts + 0.2, 33)  # 33ms без детекции
    
    states = attr_manager.get_states(track_id)
    state = states.get(attr_name)
    print(f"Состояние: {state.state}, confidence: {state.confidence_smooth:.3f}, total_time: {state.total_time_ms}ms, no_detect: {state.no_detect_time_ms}ms")
    
    print("\n--- Шаг 4: Продолжаем отсутствие детекции ---")
    attr_manager.update(track_id, attr_name, False, 0.0, now_ts + 0.3, 100)  # еще 100ms без детекции
    
    states = attr_manager.get_states(track_id)
    state = states.get(attr_name)
    print(f"Состояние: {state.state}, confidence: {state.confidence_smooth:.3f}, total_time: {state.total_time_ms}ms, no_detect: {state.no_detect_time_ms}ms")
    
    print("\n--- Шаг 5: Еще больше отсутствия детекции ---")
    attr_manager.update(track_id, attr_name, False, 0.0, now_ts + 0.4, 100)  # еще 100ms без детекции
    
    states = attr_manager.get_states(track_id)
    state = states.get(attr_name)
    print(f"Состояние: {state.state}, confidence: {state.confidence_smooth:.3f}, total_time: {state.total_time_ms}ms, no_detect: {state.no_detect_time_ms}ms")
    
    print("\n--- Анализ проблемы ---")
    print(f"min_time_ms: 30ms")
    print(f"confirm_time_ms: 60ms")
    print(f"no_detect_time_ms: {state.no_detect_time_ms}ms")
    print(f"Должен ли перейти в 'lost'? {state.no_detect_time_ms >= 30}")
    print(f"Должен ли перейти в 'none'? {state.no_detect_time_ms >= 60}")
    
    if state.state == 'exists' and state.no_detect_time_ms >= 30:
        print("❌ ПРОБЛЕМА: Состояние должно быть 'lost', но остается 'exists'")
    elif state.state == 'lost' and state.no_detect_time_ms >= 60:
        print("❌ ПРОБЛЕМА: Состояние должно быть 'none', но остается 'lost'")

if __name__ == "__main__":
    test_attribute_state_transitions()


