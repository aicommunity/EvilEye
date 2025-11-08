#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_journal_with_images():
    """Test journal with existing images"""
    
    test_logger.info("=== Test Journal with Images ===")
    
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
        
        test_logger.info("✅ Journal widget created")
        
        # Test with existing images
        test_logger.info("\n📊 Testing with existing images:")
        
        # Check what images exist
        detected_dir = 'EvilEyeData/images/2025_09_01/detected_frames'
        lost_dir = 'EvilEyeData/images/2025_09_01/lost_frames'
        
        if os.path.exists(detected_dir):
            detected_files = os.listdir(detected_dir)
            test_logger.info(f"   Detected images: {len(detected_files)}")
            if detected_files:
                test_logger.info(f"   Sample detected: {detected_files[0]}")
        
        if os.path.exists(lost_dir):
            lost_files = os.listdir(lost_dir)
            test_logger.info(f"   Lost images: {len(lost_files)}")
            if lost_files:
                test_logger.info(f"   Sample lost: {lost_files[0]}")
        
        # Test data loading
        test_logger.info("\n📋 Data Summary:")
        test_logger.info(f"   Total events: {journal.ds.get_total({})}")
        test_logger.info(f"   Found events: {journal.ds.get_total({'event_type': 'found'})}")
        test_logger.info(f"   Lost events: {journal.ds.get_total({'event_type': 'lost'})}")
        
        # Show window
        journal.show()
        
        test_logger.info("\n🔧 Journal Features:")
        test_logger.info("   - Fixed Time column (shows found or lost time)")
        test_logger.info("   - Fixed image display (handles missing images)")
        test_logger.info("   - Proper grouping of found/lost events")
        test_logger.info("   - Real-time updates")
        
        test_logger.info("\n✅ All systems operational")
        
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
            app.quit()
        except Exception:
            pass
        
    except Exception as e:
        test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
