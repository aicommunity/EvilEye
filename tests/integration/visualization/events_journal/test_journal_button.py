#!/usr/bin/env python3

import sys
import os
try:
    from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget
    from PyQt6.QtCore import Qt
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget
    from PyQt5.QtCore import Qt
    pyqt_version = 5

from evileye.visualization_modules.main_window import MainWindow

def test_journal_button_behavior(journal_test_logger, qapp):
    try:
        from PyQt6.QtCore import QTimer
    except ImportError:
        from PyQt5.QtCore import QTimer
    
    # Use QApplication managed by pytest-qt fixture.
    app = qapp
    
    # Test 1: use_database = True
    journal_test_logger.info("=== Test 1: use_database = True ===")
    class MockControllerDB:
        def __init__(self):
            self.use_database = True
            self.database_config = {
                'database': {
                    'image_dir': 'EvilEyeData',
                    'database_name': 'test_db',
                    'host_name': 'localhost',
                    'port': 5432,
                    'user_name': 'test_user',
                    'password': 'test_pass'
                },
                'database_adapters': {
                    'objects': {
                        'table_name': 'objects'
                    }
                },
                'tables': {
                    'objects': 'objects'
                }
            }
            self.enable_close_from_gui = True
            self.show_main_gui = True
            self.show_journal = False
            
        def is_running(self):
            return True
            
        def set_current_main_widget_size(self, width, height):
            pass
    
    controller_db = MockControllerDB()
    
    config = {
        'visualizer': {
            'num_height': 1,
            'num_width': 1
        },
        'pipeline': {
            'sources': [
                {
                    'source_ids': [0]
                }
            ]
        },
        'events_detectors': {
            'ZoneEventsDetector': {
                'sources': {}
            }
        }
    }
    
    # MainWindow API has changed: create window first, then set controller+params.
    main_window_db = MainWindow(800, 600)
    main_window_db.set_controller(controller_db, 'test_config.json', config)
    # In DB mode journal initialization happens asynchronously; actions can be disabled until ready.
    journal_test_logger.info(f"DB mode - Objects journal enabled: {main_window_db.objects_journal.isEnabled()}")
    journal_test_logger.info(f"DB mode - Events journal enabled: {main_window_db.events_journal.isEnabled()}")
    journal_test_logger.info(f"DB mode - Objects journal tooltip: {main_window_db.objects_journal.toolTip()}")
    journal_test_logger.info(f"DB mode - Events journal tooltip: {main_window_db.events_journal.toolTip()}")
    main_window_db.close()
    
    # Test 2: use_database = False, journal created successfully
    journal_test_logger.info("\n=== Test 2: use_database = False, journal created ===")
    class MockControllerJSON:
        def __init__(self):
            self.use_database = False
            self.database_config = {
                'database': {
                    'image_dir': 'EvilEyeData'
                }
            }
            self.enable_close_from_gui = True
            self.show_main_gui = True
            self.show_journal = False
            
        def is_running(self):
            return True
            
        def set_current_main_widget_size(self, width, height):
            pass
    
    controller_json = MockControllerJSON()
    
    # Ensure default images directory exists so JSON journal can be created.
    os.makedirs("EvilEyeData", exist_ok=True)

    main_window_json = MainWindow(800, 600)
    main_window_json.set_controller(controller_json, 'test_config.json', config)
    journal_test_logger.info(f"JSON mode - Objects journal enabled: {main_window_json.objects_journal.isEnabled()}")
    journal_test_logger.info(f"JSON mode - Events journal enabled: {main_window_json.events_journal.isEnabled()}")
    journal_test_logger.info(f"JSON mode - Objects journal tooltip: {main_window_json.objects_journal.toolTip()}")
    journal_test_logger.info(f"JSON mode - Events journal tooltip: {main_window_json.events_journal.toolTip()}")
    main_window_json.close()
    
    # Test 3: use_database = False, journal creation failed
    journal_test_logger.info("\n=== Test 3: use_database = False, journal creation failed ===")
    class MockControllerFailed:
        def __init__(self):
            self.use_database = False
            self.database_config = {
                'database': {
                    'image_dir': '/invalid/path/that/will/fail'
                }
            }
            self.enable_close_from_gui = True
            self.show_main_gui = True
            self.show_journal = False
            
        def is_running(self):
            return True
            
        def set_current_main_widget_size(self, width, height):
            pass
    
    controller_failed = MockControllerFailed()
    
    main_window_failed = MainWindow(800, 600)
    main_window_failed.set_controller(controller_failed, 'test_config.json', config)
    journal_test_logger.info(f"Failed mode - Objects journal enabled: {main_window_failed.objects_journal.isEnabled()}")
    journal_test_logger.info(f"Failed mode - Events journal enabled: {main_window_failed.events_journal.isEnabled()}")
    main_window_failed.close()
    
    # Закрываем все окна и корректно выходим (без принудительного app.quit()).
    def close_all():
        for widget in app.allWidgets():
            if widget.isWindow():
                widget.close()
        app.exit()

    QTimer.singleShot(50, close_all)
    try:
        app.processEvents()
    except Exception:
        pass
    
    journal_test_logger.info("\n=== Test completed ===")
