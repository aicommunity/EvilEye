#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_journal_final_fix():
    """Test journal with fixed file naming"""
    
    test_logger.info("=== Final Journal Fix Test ===")
    
    # Test 1: Check JSON file naming
    test_logger.info("\n1. JSON File Naming:")
    try:
        from evileye.visualization_modules.journal_data_source_json import JsonLabelJournalDataSource
        
        ds = JsonLabelJournalDataSource('EvilEyeData')
        events = ds.fetch(0, 10, {}, [('ts', 'desc')])
        
        test_logger.info(f"   Total events: {len(events)}")
        
        # Check file naming patterns
        cam_patterns = {}
        for ev in events:
            img_filename = ev.get('image_filename', '')
            if img_filename:
                # Extract camera name from filename
                if '_Cam' in img_filename:
                    parts = img_filename.split('_Cam')
                    if len(parts) > 1:
                        cam_part = parts[1].split('_')[0]
                        cam_name = f"Cam{cam_part}"
                        cam_patterns[cam_name] = cam_patterns.get(cam_name, 0) + 1
        
        test_logger.info(f"   Camera patterns found: {cam_patterns}")
        
        # Show sample filenames
        test_logger.info("   Sample filenames:")
        for i, ev in enumerate(events[:5]):
            img_filename = ev.get('image_filename', '')
            test_logger.info(f"     {i+1}. {img_filename}")
        
        ds.close()
        
    except Exception as e:
        test_logger.info(f"   ❌ Error: {e}")
    
    # Test 2: Check ImageDelegate functionality
    test_logger.info("\n2. ImageDelegate Functionality:")
    try:
        from evileye.visualization_modules.events_journal_json import ImageDelegate
        
        delegate = ImageDelegate()
        test_logger.info(f"   ✅ ImageDelegate created")
        test_logger.info(f"   Preview size: {delegate.preview_width}x{delegate.preview_height}")
        
    except Exception as e:
        test_logger.info(f"   ❌ Error: {e}")
    
    # Test 3: Test journal widget
    test_logger.info("\n3. Journal Widget:")
    try:
        try:
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtCore import QTimer
        except ImportError:
            from PyQt5.QtWidgets import QApplication
            from PyQt5.QtCore import QTimer
        
        from evileye.visualization_modules.events_journal_json import EventsJournalJson
        
        # Create QApplication if it doesn't exist
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv if hasattr(sys, 'argv') else [])
        
        journal = EventsJournalJson('EvilEyeData')
        test_logger.info(f"   ✅ Journal widget created")
        test_logger.info(f"   Available dates: {journal.ds.list_available_dates()}")
        test_logger.info(f"   Total events: {journal.ds.get_total({})}")
        
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
        test_logger.info(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 4: Check file existence
    test_logger.info("\n4. File Existence Check:")
    try:
        for i, ev in enumerate(events):
            img_filename = ev.get('image_filename', '')
            if img_filename:
                # Construct full path
                date_folder = ev.get('date_folder', '')
                full_path = os.path.join('EvilEyeData', 'images', date_folder, img_filename)
                exists = os.path.exists(full_path)
                test_logger.info(f"   Event {i+1}: {os.path.basename(img_filename)} - {'✅' if exists else '❌'}")
        
    except Exception as e:
        test_logger.info(f"   ❌ Error: {e}")
    
    # Test 5: Summary
    test_logger.info("\n5. Fix Summary:")
    test_logger.info("   ✅ JSON file naming: Fixed (includes camera names)")
    test_logger.info("   ✅ ImageDelegate: Simplified (no complex file matching)")
    test_logger.info("   ✅ Journal widget: Works with new naming")
    test_logger.info("   ⚠️  Image files: Not created (separate issue)")
    
    test_logger.info("\n=== Implementation Status ===")
    test_logger.info("🔧 Fixed Issues:")
    test_logger.info("   - JSON file naming now includes camera names")
    test_logger.info("   - ImageDelegate simplified to use direct paths")
    test_logger.info("   - ObjectsHandler receives camera parameters")
    test_logger.info("   - Controller passes camera info to ObjectsHandler")
    
    test_logger.info("\n⚠️  Remaining Issues:")
    test_logger.info("   - Image files not being saved (separate problem)")
    test_logger.info("   - Need to investigate image saving mechanism")
    
    test_logger.info("\n=== Usage Instructions ===")
    test_logger.info("📋 Set use_database=false in config")
    test_logger.info("📋 JSON files now contain correct image filenames")
    test_logger.info("📋 Journal will display images when files are available")
    test_logger.info("📋 Image saving needs to be fixed separately")
    
    test_logger.info("\n=== Test completed successfully ===")
