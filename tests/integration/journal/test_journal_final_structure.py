#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_journal_final_structure():
    """Test journal with correct folder structure"""
    
    test_logger.info("=== Final Journal Structure Test ===")
    
    # Test 1: Check folder structure
    test_logger.info("\n1. Folder Structure Verification:")
    base_dir = 'EvilEyeData'
    images_dir = os.path.join(base_dir, 'images')
    
    test_logger.info(f"   Base directory: {base_dir} - {'✅' if os.path.exists(base_dir) else '❌'}")
    test_logger.info(f"   Images directory: {images_dir} - {'✅' if os.path.exists(images_dir) else '❌'}")
    
    if os.path.exists(images_dir):
        dates = [d for d in os.listdir(images_dir) 
                if os.path.isdir(os.path.join(images_dir, d)) and d[:4].isdigit()]
        test_logger.info(f"   Date folders found: {len(dates)}")
        for date in dates[:3]:  # Show first 3
            date_path = os.path.join(images_dir, date)
            found_file = os.path.join(date_path, 'objects_found.json')
            lost_file = os.path.join(date_path, 'objects_lost.json')
            detected_frames = os.path.join(date_path, 'detected_frames')
            lost_frames = os.path.join(date_path, 'lost_frames')
            
            test_logger.info(f"   📁 {date}:")
            test_logger.info(f"      objects_found.json: {'✅' if os.path.exists(found_file) else '❌'}")
            test_logger.info(f"      objects_lost.json: {'✅' if os.path.exists(lost_file) else '❌'}")
            test_logger.info(f"      detected_frames/: {'✅' if os.path.exists(detected_frames) else '❌'}")
            test_logger.info(f"      lost_frames/: {'✅' if os.path.exists(lost_frames) else '❌'}")
    
    # Test 2: Test JSON data source
    test_logger.info("\n2. JSON Data Source Test:")
    try:
        from evileye.visualization_modules.journal_data_source_json import JsonLabelJournalDataSource
        
        ds = JsonLabelJournalDataSource(base_dir)
        dates = ds.list_available_dates()
        test_logger.info(f"   Available dates: {dates}")
        
        total_events = ds.get_total({})
        found_events = ds.get_total({'event_type': 'found'})
        lost_events = ds.get_total({'event_type': 'lost'})
        
        test_logger.info(f"   Total events: {total_events}")
        test_logger.info(f"   Found events: {found_events}")
        test_logger.info(f"   Lost events: {lost_events}")
        
        # Test fetching
        events = ds.fetch(0, 5, {}, [('ts', 'desc')])
        test_logger.info(f"   First 5 events:")
        for i, ev in enumerate(events):
            test_logger.info(f"     {i+1}. {ev.get('event_type')} - {ev.get('class_name')} - {ev.get('ts')}")
        
        ds.close()
        
    except Exception as e:
        test_logger.info(f"   ❌ Error: {e}")
    
    # Test 3: Test journal widget
    test_logger.info("\n3. Journal Widget Test:")
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
        
        journal = EventsJournalJson(base_dir)
        test_logger.info(f"   ✅ Journal widget created successfully")
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
        test_logger.info(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 4: Configuration test
    test_logger.info("\n4. Configuration Test:")
    configs = [
        ('configs/pipeline_capture.json', 'JSON mode'),
        ('configs/pipeline_capture_no_dir.json', 'JSON mode (no dir)'),
        ('configs/pipeline_capture_db.json', 'Database mode')
    ]
    
    for config_file, description in configs:
        if os.path.exists(config_file):
            import json
            with open(config_file, 'r') as f:
                config = json.load(f)
            
            use_database = config.get('controller', {}).get('use_database', True)
            image_dir = config.get('database', {}).get('image_dir', 'EvilEyeData')
            image_dir_exists = os.path.exists(image_dir)
            
            test_logger.info(f"   {description}:")
            test_logger.info(f"      use_database={use_database}, image_dir='{image_dir}', exists={image_dir_exists}")
            
            if not use_database:
                if image_dir_exists:
                    test_logger.info(f"      Expected: JSON journal enabled")
                else:
                    test_logger.info(f"      Expected: JSON journal disabled")
            else:
                test_logger.info(f"      Expected: Database journal")
    
    test_logger.info("\n=== Expected Structure ===")
    test_logger.info("📁 images_dir/")
    test_logger.info("   📁 images/")
    test_logger.info("      📁 YYYY_MM_DD/")
    test_logger.info("         📄 objects_found.json")
    test_logger.info("         📄 objects_lost.json")
    test_logger.info("         📁 detected_frames/")
    test_logger.info("         📁 detected_previews/")
    test_logger.info("         📁 lost_frames/")
    test_logger.info("         📁 lost_previews/")
    
    test_logger.info("\n=== Test completed successfully ===")
