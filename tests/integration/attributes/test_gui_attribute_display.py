#!/usr/bin/env python3
"""
Тест отображения атрибутов в GUI с новой информацией
"""

import cv2
import numpy as np
from evileye.utils.utils import draw_object_attributes

def test_gui_attribute_display():
    """Тест отображения атрибутов в GUI"""
    print("=== Тест отображения атрибутов в GUI ===")
    
    # Создаем тестовое изображение
    image = np.zeros((400, 600, 3), dtype=np.uint8)
    
    # Создаем мок-объект с атрибутами
    class MockObject:
        def __init__(self):
            self.attributes = {
                'hard_hat': {
                    'state': 'exists',
                    'confidence_smooth': 0.85,
                    'total_time_ms': 1500,
                    'total_found_time_ms': 2000,
                    'total_lost_time_ms': 500,
                    'found_ratio': 0.8
                },
                'no_hard_hat': {
                    'state': 'lost',
                    'confidence_smooth': 0.12,
                    'total_time_ms': 0,
                    'total_found_time_ms': 300,
                    'total_lost_time_ms': 1200,
                    'found_ratio': 0.2
                },
                'safety_vest': {
                    'state': 'none',
                    'confidence_smooth': 0.0,
                    'total_time_ms': 0,
                    'total_found_time_ms': 100,
                    'total_lost_time_ms': 1500,
                    'found_ratio': 0.06
                }
            }
    
    obj = MockObject()
    bbox = [50, 50, 200, 150]  # Тестовый bounding box
    
    config = {
        'font_size_pt': 12,
        'font_face': cv2.FONT_HERSHEY_SIMPLEX,
        'thickness': 2,
        'font_scale_method': 'resolution_based',
        'base_resolution': (1920, 1080)
    }
    
    print("\n--- Атрибуты объекта ---")
    for attr_name, attr_data in obj.attributes.items():
        state = attr_data.get('state', 'none')
        confidence = attr_data.get('confidence_smooth', 0.0)
        total_found_time = attr_data.get('total_found_time_ms', 0)
        total_lost_time = attr_data.get('total_lost_time_ms', 0)
        found_ratio = attr_data.get('found_ratio', 0.0)
        
        # Рассчитываем суммарное время (или ноль если < 0)
        summary_time = max(0, total_found_time - total_lost_time)
        
        print(f"{attr_name}:")
        print(f"  Состояние: {state}")
        print(f"  Доверие: {confidence:.2f}")
        print(f"  Время обнаружения: {total_found_time}ms")
        print(f"  Время потери: {total_lost_time}ms")
        print(f"  Суммарное время: {summary_time}ms")
        print(f"  Found ratio: {found_ratio:.1%}")
        print()
    
    # Рисуем атрибуты
    font_face = config['font_face']
    font_scale = 0.5  # 0.5x от основного шрифта
    thickness = config['thickness']
    draw_object_attributes(image, obj, bbox, font_face, font_scale, thickness)
    
    # Сохраняем результат в tests/data/images/
    from pathlib import Path
    output_dir = Path(__file__).parent.parent.parent.parent / "data" / "images"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_filename = output_dir / "test_gui_attributes.jpg"
    cv2.imwrite(str(output_filename), image)
    print(f"Сохранено: {output_filename}")
    
    print("\n--- Новый формат отображения ---")
    print("Формат: attr_name: state (confidence, summary_time_ms, found_ratio%)")
    print("Примеры:")
    print("  hard_hat: exists (0.85, 1500ms, 80.0%)")
    print("  no_hard_hat: lost (0.12, 0ms, 20.0%)")
    print("  safety_vest: none (0.00, 0ms, 6.0%)")
    
    print("\n--- Объяснение полей ---")
    print("✅ Состояние: none/exists/lost")
    print("✅ Доверие: EMA-сглаженное значение confidence")
    print("✅ Суммарное время: max(0, found_time - lost_time)")
    print("✅ Found ratio: Процент времени обнаружения")

if __name__ == "__main__":
    test_gui_attribute_display()
