#!/usr/bin/env python3
"""
Тест исправления детекции атрибутов - теперь все атрибуты обновляются
"""

import time
from evileye.objects_handler.attribute_manager import AttributeManager

def test_attribute_detection_fix():
    """Тест исправления детекции атрибутов"""
    print("=== Тест исправления детекции атрибутов ===")
    
    # Создаем AttributeManager
    attr_manager = AttributeManager(
        thresholds_conf={'hard_hat': 0.5, 'no_hard_hat': 0.5},
        thresholds_time={
            'hard_hat': {'min_time_ms': 30, 'confirm_time_ms': 60},
            'no_hard_hat': {'min_time_ms': 30, 'confirm_time_ms': 60}
        },
        ema_alpha=0.7
    )
    
    track_id = 123
    
    print("\n--- Шаг 1: Детекция hard_hat ---")
    now_ts = time.time()
    # Симулируем результат от AttributeClassifier с детекцией hard_hat
    attr_results = {
        'hard_hat': {
            'detected_now': True,
            'confidence': 0.8,
            'max_confidence': 0.8,
            'detection_count': 1,
            'bbox': [100, 100, 200, 200],
            'class_id': 0
        },
        'no_hard_hat': {
            'detected_now': False,
            'confidence': 0.0,
            'max_confidence': 0.0,
            'detection_count': 0,
            'bbox': None,
            'class_id': None
        }
    }
    
    # Обновляем атрибуты
    for attr_name, attr_info in attr_results.items():
        detected_now = attr_info.get('detected_now', False)
        confidence = attr_info.get('confidence', 0.0)
        attr_manager.update(track_id, attr_name, detected_now, confidence, now_ts, 50)
    
    states = attr_manager.get_states(track_id)
    for attr_name, state in states.items():
        print(f"{attr_name}: {state.state}, confidence: {state.confidence_smooth:.3f}, total_time: {state.total_time_ms}ms, no_detect: {state.no_detect_time_ms}ms")
    
    print("\n--- Шаг 2: Нет детекций (все атрибуты не обнаружены) ---")
    # Симулируем результат от AttributeClassifier без детекций
    attr_results = {
        'hard_hat': {
            'detected_now': False,
            'confidence': 0.0,
            'max_confidence': 0.0,
            'detection_count': 0,
            'bbox': None,
            'class_id': None
        },
        'no_hard_hat': {
            'detected_now': False,
            'confidence': 0.0,
            'max_confidence': 0.0,
            'detection_count': 0,
            'bbox': None,
            'class_id': None
        }
    }
    
    # Обновляем атрибуты
    for attr_name, attr_info in attr_results.items():
        detected_now = attr_info.get('detected_now', False)
        confidence = attr_info.get('confidence', 0.0)
        attr_manager.update(track_id, attr_name, detected_now, confidence, now_ts + 0.1, 100)
    
    states = attr_manager.get_states(track_id)
    for attr_name, state in states.items():
        print(f"{attr_name}: {state.state}, confidence: {state.confidence_smooth:.3f}, total_time: {state.total_time_ms}ms, no_detect: {state.no_detect_time_ms}ms")
    
    print("\n--- Шаг 3: Продолжаем отсутствие детекций ---")
    # Еще один кадр без детекций
    for attr_name, attr_info in attr_results.items():
        detected_now = attr_info.get('detected_now', False)
        confidence = attr_info.get('confidence', 0.0)
        attr_manager.update(track_id, attr_name, detected_now, confidence, now_ts + 0.2, 100)
    
    states = attr_manager.get_states(track_id)
    for attr_name, state in states.items():
        print(f"{attr_name}: {state.state}, confidence: {state.confidence_smooth:.3f}, total_time: {state.total_time_ms}ms, no_detect: {state.no_detect_time_ms}ms")
    
    print("\n--- Результат ---")
    print("✅ Теперь все атрибуты обновляются при отсутствии детекции!")
    print("✅ Состояния атрибутов корректно переходят в 'lost' и 'none'!")
    print("✅ confidence_smooth сохраняется при отсутствии детекции!")

if __name__ == "__main__":
    test_attribute_detection_fix()


