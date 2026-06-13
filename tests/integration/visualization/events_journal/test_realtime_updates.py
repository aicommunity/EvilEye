#!/usr/bin/env python3

import sys
import os
import time
import threading

def test_realtime_updates(journal_test_logger):
    """Test real-time updates in journal window"""
    
    journal_test_logger.info("=== Test Real-time Updates ===")
    
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QTimer
        from evileye.visualization_modules.events_journal_json import EventsJournalJson
        import cv2
        import numpy as np
        import datetime
        import json
        
        # Create a simple test application
        app = QApplication([])
        
        # Create test directory structure
        base_dir = 'EvilEyeData'
        today = datetime.date.today().strftime('%Y_%m_%d')
        test_images_dir = os.path.join(base_dir, 'images', today)
        os.makedirs(test_images_dir, exist_ok=True)
        
        # Create test JSON data
        test_json_path = os.path.join(test_images_dir, 'objects_found.json')
        
        def create_test_data(object_id, timestamp):
            """Create test data with given object_id and timestamp"""
            return {
                "metadata": {
                    "version": "1.0",
                    "created": timestamp,
                    "description": "Test data",
                    "total_objects": 1
                },
                "objects": [
                    {
                        "object_id": object_id,
                        "frame_id": object_id,
                        "timestamp": timestamp,
                        "image_filename": f"detected_previews/test_preview_{object_id}.jpeg",
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
        
        # Create initial test data
        initial_data = create_test_data(1, datetime.datetime.now().isoformat())
        with open(test_json_path, 'w') as f:
            json.dump(initial_data, f, indent=2)
        
        journal_test_logger.info(f"✅ Created initial test data: {test_json_path}")
        
        # Create EventsJournalJson widget
        journal = EventsJournalJson(base_dir)
        journal.show()
        
        journal_test_logger.info("\n🧪 Testing Real-time Updates:")
        journal_test_logger.info("   - Journal window should be visible")
        journal_test_logger.info("   - Initial data should be loaded")
        journal_test_logger.info("   - New objects will be added every 5 seconds")
        journal_test_logger.info("   - Journal should update automatically")
        journal_test_logger.info("   - Press Ctrl+C to exit this test")
        
        # Flag to stop the background thread
        stop_thread = threading.Event()
        
        # Function to add new objects
        def add_new_object():
            object_id = 2
            while not stop_thread.is_set():
                try:
                    # Wait with timeout to check stop flag
                    if stop_thread.wait(timeout=5):
                        break  # Stop flag was set
                    
                    # Create new object data
                    new_data = create_test_data(object_id, datetime.datetime.now().isoformat())
                    
                    # Read existing data
                    try:
                        with open(test_json_path, 'r') as f:
                            existing_data = json.load(f)
                    except FileNotFoundError:
                        existing_data = {"metadata": {}, "objects": []}
                    
                    # Add new object to existing data
                    existing_data["objects"].extend(new_data["objects"])
                    existing_data["metadata"]["total_objects"] = len(existing_data["objects"])
                    
                    # Write updated data
                    with open(test_json_path, 'w') as f:
                        json.dump(existing_data, f, indent=2)
                    
                    journal_test_logger.info(f"✅ Added new object {object_id} at {datetime.datetime.now().strftime('%H:%M:%S')}")
                    object_id += 1
                    
                except Exception as e:
                    journal_test_logger.error(f"❌ Error adding new object: {e}")
                    break
        
        # Start background thread to add objects
        update_thread = threading.Thread(target=add_new_object, daemon=True)
        update_thread.start()
        
        # Set up a timer to check if updates are working
        def check_updates():
            row_count = journal.table.rowCount()
            journal_test_logger.info(f"📊 Current table rows: {row_count}")
            
            # Check if timer is running
            if hasattr(journal, 'update_timer') and journal.update_timer.isActive():
                journal_test_logger.info("✅ Update timer is active")
            else:
                journal_test_logger.info("❌ Update timer is not active")
        
        timer = QTimer()
        timer.timeout.connect(check_updates)
        timer.start(10000)  # Check every 10 seconds
        
        # Автоматически закрываем окно через 200ms
        def close_window():
            try:
                # Останавливаем фоновый поток
                stop_thread.set()
                # Ждем завершения потока (максимум 1 секунда)
                update_thread.join(timeout=1.0)
                
                # Останавливаем проверочный таймер
                if hasattr(timer, 'stop'):
                    timer.stop()
                
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
            except Exception:
                pass
        
        QTimer.singleShot(200, close_window)
        # Даем время на закрытие окна и обработку событий (ДО app.quit())
        # Просто ждем, чтобы QTimer.singleShot успел выполниться
        # Не вызываем app.processEvents() в цикле, чтобы избежать segfault
        time.sleep(0.3)  # Увеличиваем задержку
        
        # Явно закрываем окно на случай, если таймер не сработал
        try:
            # Останавливаем фоновый поток
            stop_thread.set()
            # Ждем завершения потока (максимум 1 секунда)
            update_thread.join(timeout=1.0)
            
            # Останавливаем проверочный таймер
            if hasattr(timer, 'stop'):
                timer.stop()
            
            # Останавливаем таймер перед закрытием
            if hasattr(journal, 'update_timer'):
                journal.update_timer.stop()
            
            # Закрываем виджет
            journal.close()
            # Закрываем data source
            if hasattr(journal, 'ds') and journal.ds:
                journal.ds.close()
            # Не вызываем app.quit() здесь, так как он уже вызван в close_window()
        except Exception:
            pass
        
    except KeyboardInterrupt:
        journal_test_logger.info("\n✅ Test interrupted by user")
    except Exception as e:
        journal_test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
