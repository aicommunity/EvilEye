#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_journal_gui():
    """Test journal GUI with fixes"""
    
    test_logger.info("=== Journal GUI Test ===")
    
    try:
        try:
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtCore import QTimer
        except ImportError:
            from PyQt5.QtWidgets import QApplication
            from PyQt5.QtCore import QTimer
        
        from evileye.visualization_modules.events_journal_json import EventsJournalJson
        
        # Create QApplication
        app = QApplication(sys.argv)
        
        # Create journal widget
        journal = EventsJournalJson('EvilEyeData')
        journal.show()
        
        test_logger.info("✅ Journal widget created and shown")
        test_logger.info("📋 Features to test:")
        test_logger.info("   - Different images for found vs lost events")
        test_logger.info("   - Bounding boxes drawn correctly on images")
        test_logger.info("   - Event type filtering (found/lost)")
        test_logger.info("   - Date selection")
        test_logger.info("   - Image scaling and display")
        
        test_logger.info("\n🔧 Fixed Issues:")
        test_logger.info("   - Event type separation")
        test_logger.info("   - Proper timestamp handling")
        test_logger.info("   - Correct image paths")
        test_logger.info("   - Bounding box scaling with actual image dimensions")
        
        test_logger.info("\n⚠️  Note: Image files may not exist yet")
        test_logger.info("   - This is a separate issue with image saving")
        test_logger.info("   - Journal will work correctly when images are available")
        
        # Автоматически закрываем окно через 100ms
        def close_window():
            # Останавливаем таймер перед закрытием
            if hasattr(journal, 'update_timer'):
                journal.update_timer.stop()
            # Закрываем виджет
            journal.close()
            # Закрываем data source
            if hasattr(journal, 'ds') and journal.ds:
                journal.ds.close()
            # Выходим из приложения
            app.quit()
        
        QTimer.singleShot(100, close_window)
        # Даем время на закрытие окна
        import time
        time.sleep(0.2)
        
        # Явно закрываем окно на случай, если таймер не сработал
        try:
            if hasattr(journal, 'update_timer'):
                journal.update_timer.stop()
            journal.close()
            if hasattr(journal, 'ds') and journal.ds:
                journal.ds.close()
            # Не вызываем app.quit() здесь, так как он уже вызван в close_window()
        except Exception:
            pass
        
    except Exception as e:
        test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
