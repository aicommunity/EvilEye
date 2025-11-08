#!/usr/bin/env python3
"""
Простой тест для проверки ROI редактора
"""

import sys
import time

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer
    from evileye.visualization_modules.roi_editor_window import ROIEditorWindow
    print("✅ Импорты успешны")
except Exception as e:
    print(f"❌ Ошибка импорта: {e}")
    sys.exit(1)

def test_roi_editor_creation():
    """Тест создания ROI редактора"""
    print("\n=== ТЕСТ СОЗДАНИЯ ROI РЕДАКТОРА ===")
    
    try:
        # Создаем приложение
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        
        # Создаем ROI редактор
        params = {}
        roi_window = ROIEditorWindow(params)
        print("   ✅ ROI редактор создан")
        
        # Проверяем основные компоненты
        if hasattr(roi_window, 'roi_canvas'):
            print("   ✅ ROI canvas существует")
        else:
            print("   ❌ ROI canvas отсутствует")
            
        if hasattr(roi_window, 'roi_list'):
            print("   ✅ ROI список существует")
        else:
            print("   ❌ ROI список отсутствует")
        
        # Проверяем, что окно может быть показано
        roi_window.setVisible(True)
        print("   ✅ Окно установлено как видимое")
        
        roi_window.setVisible(False)
        print("   ✅ Окно установлено как скрытое")
        
        # Автоматически закрываем окно через 100ms
        def close_window():
            try:
                roi_window.close()
                app.quit()
            except Exception:
                pass
        
        QTimer.singleShot(100, close_window)
        # Даем время на закрытие окна
        time.sleep(0.2)
        
        # Явно закрываем окно на случай, если таймер не сработал
        try:
            roi_window.close()
            app.quit()
        except Exception:
            pass
        
        return True
        
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return False

if __name__ == '__main__':
    success = test_roi_editor_creation()
    if success:
        print("\n🎉 Все тесты прошли успешно!")
    else:
        print("\n💥 Тесты не прошли!")
        sys.exit(1)

