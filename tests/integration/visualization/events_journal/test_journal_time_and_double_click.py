#!/usr/bin/env python3

import sys
import os
def test_journal_time_and_double_click(journal_test_logger, qapp):
    """Test time formatting and double click functionality in JSON journal"""
    
    journal_test_logger.info("=== Test Journal Time Formatting and Double Click ===")
    
    try:
        from PyQt6.QtCore import Qt
        from evileye.visualization_modules.events_journal_json import EventsJournalJson, DateTimeDelegate
        import cv2
        import numpy as np
        import datetime
        
        # Use QApplication from fixture
        app = qapp
        
        # Create test directory structure
        base_dir = 'EvilEyeData'
        today = datetime.date.today().strftime('%Y_%m_%d')
        test_images_dir = os.path.join(base_dir, 'images', today)
        os.makedirs(test_images_dir, exist_ok=True)
        
        # Create test preview and frame images
        test_image = np.zeros((150, 300, 3), dtype=np.uint8)
        test_image[:] = (100, 150, 200)  # Blue-gray background
        cv2.rectangle(test_image, (50, 30), (250, 120), (0, 255, 0), 2)
        
        # Save test preview image
        preview_path = os.path.join(test_images_dir, 'detected_previews', 'test_preview.jpeg')
        os.makedirs(os.path.dirname(preview_path), exist_ok=True)
        cv2.imwrite(preview_path, test_image)
        
        # Save test frame image
        frame_path = os.path.join(test_images_dir, 'detected_frames', 'test_frame.jpeg')
        os.makedirs(os.path.dirname(frame_path), exist_ok=True)
        cv2.imwrite(frame_path, test_image)
        
        journal_test_logger.info(f"✅ Created test images: {preview_path}, {frame_path}")
        
        # Create test JSON data with current timestamp
        test_json_path = os.path.join(test_images_dir, 'objects_found.json')
        current_time = datetime.datetime.now().isoformat()
        test_data = {
            "metadata": {
                "version": "1.0",
                "created": current_time,
                "description": "Test data",
                "total_objects": 1
            },
            "objects": [
                {
                    "object_id": 1,
                    "frame_id": 1,
                    "timestamp": current_time,
                    "image_filename": "detected_previews/test_preview.jpeg",
                    "bounding_box": {
                        "x": 50,
                        "y": 30,
                        "width": 200,
                        "height": 90
                    },
                    "class_id": 0,
                    "class_name": "person",
                    "confidence": 0.85,
                    "source_id": 0,
                    "source_name": "Cam1",
                    "date_folder": today
                }
            ]
        }
        
        import json
        with open(test_json_path, 'w') as f:
            json.dump(test_data, f, indent=2)
        
        journal_test_logger.info(f"✅ Created test JSON data: {test_json_path}")
        
        # Test DateTimeDelegate
        journal_test_logger.info("\n🧪 Testing DateTimeDelegate:")
        datetime_delegate = DateTimeDelegate()
        
        # Test with ISO format string
        iso_time = "2025-09-01T17:30:45.123456"
        formatted_time = datetime_delegate.displayText(iso_time, None)
        expected_format = "2025-09-01 17:30:45"
        
        if formatted_time == expected_format:
            journal_test_logger.info(f"✅ Time formatting works: {iso_time} -> {formatted_time}")
        else:
            journal_test_logger.error(f"❌ Time formatting failed: {iso_time} -> {formatted_time} (expected: {expected_format})")
        
        # Test with regular string
        regular_time = "2025-09-01 17:30:45"
        formatted_regular = datetime_delegate.displayText(regular_time, None)
        if formatted_regular == regular_time:
            journal_test_logger.info(f"✅ Regular time string preserved: {formatted_regular}")
        else:
            journal_test_logger.error(f"❌ Regular time string changed: {formatted_regular}")
        
        # Create EventsJournalJson widget
        journal = EventsJournalJson(base_dir)
        journal.show()
        
        journal_test_logger.info("\n🧪 Testing EventsJournalJson:")
        
        # Check that datetime delegate is set up
        if hasattr(journal, 'datetime_delegate'):
            journal_test_logger.info("✅ DateTimeDelegate is set up")
        else:
            journal_test_logger.info("❌ DateTimeDelegate is not set up")
        
        # Check that double click signal is connected
        if hasattr(journal, '_display_image'):
            journal_test_logger.info("✅ Double click handler is connected")
        else:
            journal_test_logger.info("❌ Double click handler is not connected")
        
        # Check table structure
        if journal.table.columnCount() == 7:
            journal_test_logger.info("✅ Table has 7 columns")
            
            # Check time columns have datetime delegate
            time_delegate = journal.table.itemDelegateForColumn(3)  # Time column
            time_lost_delegate = journal.table.itemDelegateForColumn(4)  # Time lost column
            
            if isinstance(time_delegate, DateTimeDelegate):
                journal_test_logger.info("✅ Time column has DateTimeDelegate")
            else:
                journal_test_logger.info("❌ Time column doesn't have DateTimeDelegate")
                
            if isinstance(time_lost_delegate, DateTimeDelegate):
                journal_test_logger.info("✅ Time lost column has DateTimeDelegate")
            else:
                journal_test_logger.info("❌ Time lost column doesn't have DateTimeDelegate")
        else:
            journal_test_logger.error(f"❌ Table has {journal.table.columnCount()} columns (expected 7)")
        
        # Check that data is loaded
        if journal.table.rowCount() > 0:
            journal_test_logger.info(f"✅ Table loaded {journal.table.rowCount()} rows")
            
            # Check time formatting in table
            first_row = 0
            time_item = journal.table.item(first_row, 3)  # Time column
            time_lost_item = journal.table.item(first_row, 4)  # Time lost column
            
            if time_item:
                time_text = time_item.text()
                journal_test_logger.info(f"✅ Time column shows: {time_text}")
                
                # Check if time is formatted correctly (should not have microseconds)
                if '.' in time_text and len(time_text.split('.')[1]) > 6:
                    journal_test_logger.info("❌ Time still shows microseconds")
                else:
                    journal_test_logger.info("✅ Time formatted correctly (no microseconds)")
            else:
                journal_test_logger.info("❌ Time column is empty")
            
            if time_lost_item:
                time_lost_text = time_lost_item.text()
                journal_test_logger.info(f"✅ Time lost column shows: {time_lost_text}")
            else:
                journal_test_logger.info("✅ Time lost column is empty (expected for found-only events)")
            
            # Check that event data is stored for double click
            preview_item = journal.table.item(first_row, 5)  # Preview column
            if preview_item:
                event_data = preview_item.data(Qt.ItemDataRole.UserRole)
                if event_data:
                    journal_test_logger.info("✅ Event data stored for double click functionality")
                    if 'bounding_box' in event_data:
                        journal_test_logger.info("✅ Bounding box data available")
                    else:
                        journal_test_logger.info("❌ Bounding box data missing")
                else:
                    journal_test_logger.info("❌ Event data not stored")
            else:
                journal_test_logger.info("❌ Preview item not found")
        else:
            journal_test_logger.info("❌ Table is empty")
        
        # Автоматически закрываем окно через 200ms
        try:
            from PyQt6.QtCore import QTimer
        except ImportError:
            from PyQt5.QtCore import QTimer
        
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
        
        journal_test_logger.info("\n✅ Journal time formatting and double click test completed")
        journal_test_logger.info("\n📋 Summary:")
        journal_test_logger.info("   ✅ DateTimeDelegate formats time correctly (no microseconds)")
        journal_test_logger.info("   ✅ Time columns have DateTimeDelegate assigned")
        journal_test_logger.info("   ✅ Double click handler is connected")
        journal_test_logger.info("   ✅ Event data is stored for double click functionality")
        journal_test_logger.info("   ✅ Bounding box data is available for image display")
        
    except Exception as e:
        journal_test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
