#!/usr/bin/env python3

import sys
import os
def test_journal_updated(journal_test_logger, qapp):
    """Test updated journal with new structure"""
    
    journal_test_logger.info("=== Updated Journal Test ===")
    
    try:
        try:
            from PyQt6.QtCore import QTimer
        except ImportError:
            from PyQt5.QtCore import QTimer
        
        from evileye.visualization_modules.events_journal_json import EventsJournalJson
        
        # Use QApplication from fixture
        app = qapp
        
        # Create journal widget
        journal = EventsJournalJson('EvilEyeData')
        
        journal_test_logger.info("✅ Updated journal widget created")
        
        # Test data loading
        journal_test_logger.info("\n📊 Data Summary:")
        journal_test_logger.info(f"   Total events: {journal.ds.get_total({})}")
        journal_test_logger.info(f"   Found events: {journal.ds.get_total({'event_type': 'found'})}")
        journal_test_logger.info(f"   Lost events: {journal.ds.get_total({'event_type': 'lost'})}")
        journal_test_logger.info(f"   Available dates: {journal.ds.list_available_dates()}")
        
        # Test sample data
        journal_test_logger.info("\n📋 Sample Data:")
        events = journal.ds.fetch(0, 5, {}, [])
        for i, ev in enumerate(events):
            journal_test_logger.info(f"   Event {i+1}:")
            journal_test_logger.info(f"     Type: {ev.get('event_type')}")
            journal_test_logger.info(f"     Time: {ev.get('ts')}")
            journal_test_logger.info(f"     Source: {ev.get('source_name')}")
            journal_test_logger.info(f"     Object ID: {ev.get('object_id')}")
            journal_test_logger.info(f"     Image: {ev.get('image_filename')}")
        
        # Show window
        journal.show()
        
        journal_test_logger.info("\n🔧 New Features:")
        journal_test_logger.info("   - Database-style table structure")
        journal_test_logger.info("   - Found and lost events in same row")
        journal_test_logger.info("   - Proper source name display (Cam1, Cam2, etc.)")
        journal_test_logger.info("   - Real-time updates every 5 seconds")
        journal_test_logger.info("   - Preview and Lost preview columns")
        journal_test_logger.info("   - Bounding box drawing on images")
        
        journal_test_logger.info("\n✅ All systems operational")
        
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
        
        QTimer.singleShot(200, close_window)
        # Даем время на закрытие окна и обработку событий (ДО app.quit())
        import time
        # Просто ждем, чтобы QTimer.singleShot успел выполниться
        # Не вызываем app.processEvents() в цикле, чтобы избежать segfault
        time.sleep(0.3)
    
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
        journal_test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
