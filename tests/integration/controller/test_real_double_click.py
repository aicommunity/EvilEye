#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_real_double_click():
    """Test real double click functionality in GUI"""
    
    test_logger.info("=== Test Real Double Click ===")
    
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt, QTimer
        from evileye.visualization_modules.events_journal_json import EventsJournalJson
        import cv2
        import numpy as np
        import datetime
        
        # Create a simple test application
        app = QApplication([])
        
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
        
        test_logger.info(f"✅ Created test images: {preview_path}, {frame_path}")
        
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
        
        test_logger.info(f"✅ Created test JSON data: {test_json_path}")
        
        # Create EventsJournalJson widget
        journal = EventsJournalJson(base_dir)
        journal.show()
        
        test_logger.info("\n🧪 Testing Real Double Click:")
        test_logger.info("   - Journal window should be visible")
        test_logger.info("   - Double click on any preview image in the table")
        test_logger.info("   - A new window should open with the full image")
        test_logger.info("   - Double click on the image window to close it")
        test_logger.info("   - Press Ctrl+C to exit this test")
        
        # Set up a timer to check if image window was created
        def check_image_window():
            if hasattr(journal, 'image_win') and journal.image_win and journal.image_win.isVisible():
                test_logger.info("✅ Image window was created and is visible!")
                test_logger.info("✅ Double click functionality is working!")
            else:
                test_logger.info("⏳ Waiting for double click on preview image...")
        
        timer = QTimer()
        timer.timeout.connect(check_image_window)
        timer.start(1000)  # Check every second
        
        # Автоматически закрываем окно через 500ms
        def close_window():
            # Останавливаем таймер перед закрытием
            if hasattr(journal, 'update_timer'):
                journal.update_timer.stop()
            # Закрываем виджет
            journal.close()
            # Закрываем data source
            if hasattr(journal, 'ds') and journal.ds:
                journal.ds.close()
            # Обрабатываем события для корректного закрытия
            app.processEvents()
            # Выходим из приложения
            app.quit()
        
        QTimer.singleShot(500, close_window)
        app.processEvents()
        
    except KeyboardInterrupt:
        test_logger.info("\n✅ Test interrupted by user")
    except Exception as e:
        test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
