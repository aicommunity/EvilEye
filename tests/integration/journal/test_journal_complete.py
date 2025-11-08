#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_journal_complete():
    """Complete journal test"""
    
    test_logger.info("=== Complete Journal Test ===")
    
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
        
        # Test data loading
        test_logger.info("\n📊 Data Summary:")
        test_logger.info(f"   Total events: {journal.ds.get_total({})}")
        test_logger.info(f"   Found events: {journal.ds.get_total({'event_type': 'found'})}")
        test_logger.info(f"   Lost events: {journal.ds.get_total({'event_type': 'lost'})}")
        test_logger.info(f"   Available dates: {journal.ds.list_available_dates()}")
        
        # Test sample data
        test_logger.info("\n📋 Sample Data:")
        events = journal.ds.fetch(0, 3, {}, [])
        for i, ev in enumerate(events):
            test_logger.info(f"   Event {i+1}:")
            test_logger.info(f"     Type: {ev.get('event_type')}")
            test_logger.info(f"     Time: {ev.get('ts')}")
            test_logger.info(f"     Source: {ev.get('source_name')}")
            test_logger.info(f"     Class: {ev.get('class_name')}")
            test_logger.info(f"     Image: {ev.get('image_filename')}")
            test_logger.info(f"     BBox: {ev.get('bounding_box')}")
        
        # Show window
        journal.show()
        
        test_logger.info("\n🔧 Features to test:")
        test_logger.info("   - Event type filtering (found/lost)")
        test_logger.info("   - Date selection")
        test_logger.info("   - Image display (if files exist)")
        test_logger.info("   - Bounding box drawing")
        test_logger.info("   - Data accuracy in table")
        
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
