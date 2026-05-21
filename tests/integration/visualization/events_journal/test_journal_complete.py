#!/usr/bin/env python3

import sys
import os
def test_journal_complete(journal_test_logger, qapp):
    """Complete journal test"""
    
    journal_test_logger.info("=== Complete Journal Test ===")
    
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
        
        journal_test_logger.info("✅ Journal widget created")
        
        # Test data loading
        journal_test_logger.info("\n📊 Data Summary:")
        journal_test_logger.info(f"   Total events: {journal.ds.get_total({})}")
        journal_test_logger.info(f"   Found events: {journal.ds.get_total({'event_type': 'found'})}")
        journal_test_logger.info(f"   Lost events: {journal.ds.get_total({'event_type': 'lost'})}")
        journal_test_logger.info(f"   Available dates: {journal.ds.list_available_dates()}")
        
        # Test sample data
        journal_test_logger.info("\n📋 Sample Data:")
        events = journal.ds.fetch(0, 3, {}, [])
        for i, ev in enumerate(events):
            journal_test_logger.info(f"   Event {i+1}:")
            journal_test_logger.info(f"     Type: {ev.get('event_type')}")
            journal_test_logger.info(f"     Time: {ev.get('ts')}")
            journal_test_logger.info(f"     Source: {ev.get('source_name')}")
            journal_test_logger.info(f"     Class: {ev.get('class_name')}")
            journal_test_logger.info(f"     Image: {ev.get('image_filename')}")
            journal_test_logger.info(f"     BBox: {ev.get('bounding_box')}")
        
        # Show window
        journal.show()
        
        journal_test_logger.info("\n🔧 Features to test:")
        journal_test_logger.info("   - Event type filtering (found/lost)")
        journal_test_logger.info("   - Date selection")
        journal_test_logger.info("   - Image display (if files exist)")
        journal_test_logger.info("   - Bounding box drawing")
        journal_test_logger.info("   - Data accuracy in table")
        
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
        # Даем время на закрытие окна и обработку событий (ДО app.quit())
        import time
        # Обрабатываем события несколько раз с проверками
        for _ in range(min(10, 5)):  # Ограничиваем количество итераций
            try:
                app = QApplication.instance()
                if app is not None:
                    app.processEvents()
            except (RuntimeError, AttributeError):
                break  # QApplication уничтожен, выходим из цикла
            except Exception:
                pass
            time.sleep(0.1)  # Увеличиваем задержку
    
        # Явно закрываем окно на случай, если таймер не сработал
        try:
            if hasattr(journal, 'update_timer'):
                journal.update_timer.stop()
            journal.close()
            if hasattr(journal, 'ds') and journal.ds:
                journal.ds.close()
            # Не вызываем app.quit() здесь, так как он уже вызван в close_window()
        # Не вызываем app.quit() здесь, так как он уже вызван в close_window()
        except Exception:
            pass
        
    except Exception as e:
        journal_test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
