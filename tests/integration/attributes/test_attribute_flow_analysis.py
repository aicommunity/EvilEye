#!/usr/bin/env python3
"""
Анализ потока данных атрибутов - понимание как работают атрибуты
"""

def analyze_attribute_flow():
    """Анализ потока данных атрибутов"""
    print("=== Анализ потока данных атрибутов ===")
    
    print("\n--- 1. Где создаются атрибуты ---")
    print("✅ AttributeClassifier._classify_roi_with_detector()")
    print("   - Обрабатывает ROI изображения")
    print("   - Возвращает результаты атрибутов")
    print("   - Сохраняет в tracking_data.attr_results[track_id]")
    
    print("\n--- 2. Как передаются атрибуты ---")
    print("✅ AttributeClassifier → tracking_data.attr_results")
    print("   - tracking_data передается через пайплайн")
    print("   - ObjectsHandler получает tracking_results.attr_results")
    
    print("\n--- 3. Где обрабатываются атрибуты ---")
    print("✅ ObjectsHandler._handle_active()")
    print("   - Строка 444: if hasattr(tracking_results, 'attr_results')")
    print("   - Строка 449: attr_manager.update(track_id, attr_name, detected_now, confidence, now_ts, dt_ms)")
    
    print("\n--- 4. Неиспользуемый код ---")
    print("❌ _attr_pending - НЕ ИСПОЛЬЗУЕТСЯ")
    print("   - Инициализируется в __init__")
    print("   - Заполняется в put_attributes()")
    print("   - НО put_attributes() НИКОГДА НЕ ВЫЗЫВАЕТСЯ")
    print("   - pred в строке 455 всегда None")
    
    print("\n--- 5. put_attributes() - НЕ ИСПОЛЬЗУЕТСЯ ---")
    print("❌ put_attributes() - НИКОГДА НЕ ВЫЗЫВАЕТСЯ")
    print("   - Определен в ObjectsHandler")
    print("   - НО нигде не вызывается")
    print("   - Атрибуты приходят через tracking_results.attr_results")
    
    print("\n--- 6. Реальный поток данных ---")
    print("✅ AttributeClassifier → tracking_data.attr_results → ObjectsHandler")
    print("   - AttributeClassifier создает attr_results")
    print("   - Сохраняет в tracking_data.attr_results[track_id]")
    print("   - ObjectsHandler читает tracking_results.attr_results")
    print("   - Обновляет AttributeManager")
    print("   - Сохраняет в obj.attributes")
    
    print("\n--- 7. Что можно удалить ---")
    print("🗑️ _attr_pending: dict[int, dict[str, float]] = {}")
    print("🗑️ put_attributes() метод")
    print("🗑️ pred = self._attr_pending.pop(...) логика")
    print("🗑️ if pred: блок в _handle_active")
    
    print("\n--- 8. Что оставить ---")
    print("✅ tracking_results.attr_results обработка")
    print("✅ attr_manager.update() вызовы")
    print("✅ obj.attributes сохранение")

if __name__ == "__main__":
    analyze_attribute_flow()


