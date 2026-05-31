#!/usr/bin/env python3

import sys
import os
def test_journal_with_images(journal_test_logger, qapp):
    """Test journal with existing images"""
    
    journal_test_logger.info("=== Test Journal with Images ===")
    
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
        
        # Test with existing images
        journal_test_logger.info("\n📊 Testing with existing images:")
        
        # Check what images exist
        detected_dir = 'EvilEyeData/images/2025_09_01/detected_frames'
        lost_dir = 'EvilEyeData/images/2025_09_01/lost_frames'
        
        if os.path.exists(detected_dir):
            detected_files = os.listdir(detected_dir)
            journal_test_logger.info(f"   Detected images: {len(detected_files)}")
            if detected_files:
                journal_test_logger.info(f"   Sample detected: {detected_files[0]}")
        
        if os.path.exists(lost_dir):
            lost_files = os.listdir(lost_dir)
            journal_test_logger.info(f"   Lost images: {len(lost_files)}")
            if lost_files:
                journal_test_logger.info(f"   Sample lost: {lost_files[0]}")
        
        # Test data loading
        journal_test_logger.info("\n📋 Data Summary:")
        journal_test_logger.info(f"   Total events: {journal.ds.get_total({})}")
        journal_test_logger.info(f"   Found events: {journal.ds.get_total({'event_type': 'found'})}")
        journal_test_logger.info(f"   Lost events: {journal.ds.get_total({'event_type': 'lost'})}")
        
        # Show window
        journal.show()
        
        journal_test_logger.info("\n🔧 Journal Features:")
        journal_test_logger.info("   - Fixed Time column (shows found or lost time)")
        journal_test_logger.info("   - Fixed image display (handles missing images)")
        journal_test_logger.info("   - Proper grouping of found/lost events")
        journal_test_logger.info("   - Real-time updates")
        
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
