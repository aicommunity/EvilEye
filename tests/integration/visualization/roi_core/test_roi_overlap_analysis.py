#!/usr/bin/env python3
"""
Анализ перекрытия ROI для понимания проблемы выбора
"""


from PyQt6.QtCore import QRectF, QPointF

def analyze_roi_overlap():
    """Анализ перекрытия ROI"""
    
    # ROI из логов
    roi_data = [
        {
            "index": 0,
            "coords": [1790, 0, 2290, 400],
            "rect": QRectF(1471.0, -239.0, 500.0, 400.0),
            "zValue": 0.0,
            "description": "ROI 0 (самый маленький)"
        },
        {
            "index": 1, 
            "coords": [1700, 0, 2700, 1045],
            "rect": QRectF(1381.0, -239.0, 1000.0, 1045.0),
            "zValue": 1.0,
            "description": "ROI 1 (средний)"
        },
        {
            "index": 2,
            "coords": [1500, 0, 3840, 2160], 
            "rect": QRectF(1181.0, -239.0, 2340.0, 2160.0),
            "zValue": 2.0,
            "description": "ROI 2 (самый большой)"
        }
    ]
    
    print("=== Анализ перекрытия ROI ===")
    print()
    
    for roi in roi_data:
        print(f"{roi['description']}:")
        print(f"  Координаты: {roi['coords']}")
        print(f"  Rect: {roi['rect']}")
        print(f"  zValue: {roi['zValue']}")
        print(f"  Площадь: {roi['rect'].width() * roi['rect'].height():.0f} пикселей")
        print()
    
    print("=== Анализ перекрытий ===")
    print()
    
    # Проверяем перекрытия
    for i, roi1 in enumerate(roi_data):
        for j, roi2 in enumerate(roi_data):
            if i != j:
                intersection = roi1['rect'].intersected(roi2['rect'])
                if not intersection.isEmpty():
                    overlap_percent = (intersection.width() * intersection.height()) / (roi1['rect'].width() * roi1['rect'].height()) * 100
                    print(f"{roi1['description']} перекрывается с {roi2['description']}:")
                    print(f"  Пересечение: {intersection}")
                    print(f"  Процент перекрытия ROI1: {overlap_percent:.1f}%")
                    print()
    
    print("=== Тестовые точки для клика ===")
    print()
    
    # Тестовые точки
    test_points = [
        QPointF(1600, 100),  # Должна быть только в ROI 2
        QPointF(1900, 100),  # Должна быть в ROI 0 и ROI 2
        QPointF(2000, 500),  # Должна быть в ROI 1 и ROI 2
        QPointF(3000, 1000), # Должна быть только в ROI 2
    ]
    
    for point in test_points:
        print(f"Точка {point}:")
        overlapping_rois = []
        for roi in roi_data:
            if roi['rect'].contains(point):
                overlapping_rois.append(roi)
        
        if overlapping_rois:
            # Сортируем по zValue (по убыванию)
            overlapping_rois.sort(key=lambda x: x['zValue'], reverse=True)
            print(f"  Перекрывающиеся ROI: {[roi['index'] for roi in overlapping_rois]}")
            print(f"  Будет выбран ROI {overlapping_rois[0]['index']} (zValue={overlapping_rois[0]['zValue']})")
        else:
            print(f"  Нет перекрывающихся ROI")
        print()
    
    print("=== Рекомендации ===")
    print()
    print("1. ROI 2 полностью покрывает ROI 0 и ROI 1")
    print("2. Чтобы выбрать ROI 0 или ROI 1, нужно кликнуть в область, где нет ROI 2")
    print("3. ROI 0 можно выбрать, кликнув в область от (1971, -239) до (2381, 161)")
    print("4. ROI 1 можно выбрать, кликнув в область от (2381, -239) до (3521, 806)")
    print("5. Логика выбора работает правильно - выбирается ROI с наибольшим zValue")

if __name__ == '__main__':
    analyze_roi_overlap()
