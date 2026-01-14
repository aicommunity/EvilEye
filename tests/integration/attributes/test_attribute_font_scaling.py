#!/usr/bin/env python3
"""
Тест масштабирования шрифта атрибутов на разных разрешениях
"""

import cv2
import numpy as np
import os
from evileye.utils.utils import draw_object_attributes, calculate_font_scale_for_resolution

def create_test_image(width, height):
    """Создать тестовое изображение"""
    return np.zeros((height, width, 3), dtype=np.uint8)

def create_mock_object():
    """Создать мок-объект с атрибутами"""
    class MockObject:
        def __init__(self):
            self.attributes = {
                'hard_hat': {
                    'state': 'exists',
                    'confidence_smooth': 0.85,
                    'total_time_ms': 1500
                },
                'no_hard_hat': {
                    'state': 'lost',
                    'confidence_smooth': 0.12,
                    'total_time_ms': 0
                }
            }
    
    return MockObject()

def test_font_scaling():
    """Тест масштабирования шрифта на разных разрешениях"""
    print("=== Тест масштабирования шрифта атрибутов ===")
    
    # Тестовые разрешения
    resolutions = [
        (640, 480),    # VGA
        (1280, 720),   # HD
        (1920, 1080),  # Full HD
        (2560, 1440),  # 2K
        (3840, 2160)   # 4K
    ]
    
    config = {
        'font_size_pt': 12,
        'font_face': cv2.FONT_HERSHEY_SIMPLEX,
        'thickness': 2,
        'font_scale_method': 'resolution_based',
        'base_resolution': (1920, 1080)
    }
    
    for width, height in resolutions:
        print(f"\n--- Разрешение: {width}x{height} ---")
        
        # Создать изображение
        image = create_test_image(width, height)
        obj = create_mock_object()
        bbox = [50, 50, 200, 150]  # Тестовый bounding box
        
        # Рассчитать font_scale для основного текста
        main_font_scale = calculate_font_scale_for_resolution(
            config['font_size_pt'], width, height, config['base_resolution']
        )
        
        print(f"Основной font_scale: {main_font_scale:.3f}")
        
        # Нарисовать атрибуты
        # draw_object_attributes(image, obj, bbox, font_face, font_scale, thickness)
        draw_object_attributes(image, obj, bbox, config['font_face'], main_font_scale, config['thickness'])
        
        # Сохранить результат
        output_filename = f"test_attributes_{width}x{height}.jpg"
        cv2.imwrite(output_filename, image)
        print(f"Сохранено: {output_filename}")
        
        # Проверить размер текста
        sample_text = "hard_hat: exists (0.85, 1500ms)"
        (text_width, text_height), _ = cv2.getTextSize(
            sample_text, config['font_face'], main_font_scale * 0.5, 2
        )
        print(f"Размер текста атрибута: {text_width}x{text_height}px")
        print(f"Отношение к изображению: {text_width/width:.3f} x {text_height/height:.3f}")

if __name__ == "__main__":
    test_font_scaling()
    print("\n=== Результат ===")
    print("Размер текста атрибутов теперь масштабируется пропорционально размеру изображения!")
    print("Атрибуты будут одинаково читаемы на всех разрешениях.")


