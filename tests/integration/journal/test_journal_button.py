#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

try:
    from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget
    from PyQt6.QtCore import Qt
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget
    from PyQt5.QtCore import Qt
    pyqt_version = 5

from evileye.visualization_modules.main_window import MainWindow

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_journal_button_behavior():
    try:
        from PyQt6.QtCore import QTimer
    except ImportError:
        from PyQt5.QtCore import QTimer
    
    app = QApplication(sys.argv)
    
    # Test 1: use_database = True
    test_logger.info("=== Test 1: use_database = True ===")
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
    
    main_window_db = MainWindow(controller_db, 'test_config.json', config, 800, 600)
    if hasattr(main_window_db, 'db_journal'):
        test_logger.info(f"DB mode - Button enabled: {main_window_db.db_journal.isEnabled()}")
        test_logger.info(f"DB mode - Button text: {main_window_db.db_journal.text()}")
        test_logger.info(f"DB mode - Button tooltip: {main_window_db.db_journal.toolTip()}")
    else:
        test_logger.info("DB mode - db_journal button not available (database journal creation failed)")
    main_window_db.close()
    
    # Test 2: use_database = False, journal created successfully
    test_logger.info("\n=== Test 2: use_database = False, journal created ===")
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
    
    main_window_json = MainWindow(controller_json, 'test_config.json', config, 800, 600)
    if hasattr(main_window_json, 'db_journal'):
        test_logger.info(f"JSON mode - Button enabled: {main_window_json.db_journal.isEnabled()}")
        test_logger.info(f"JSON mode - Button text: {main_window_json.db_journal.text()}")
        test_logger.info(f"JSON mode - Button tooltip: {main_window_json.db_journal.toolTip()}")
    else:
        test_logger.info("JSON mode - db_journal button not available")
    main_window_json.close()
    
    # Test 3: use_database = False, journal creation failed
    test_logger.info("\n=== Test 3: use_database = False, journal creation failed ===")
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
    
    main_window_failed = MainWindow(controller_failed, 'test_config.json', config, 800, 600)
    if hasattr(main_window_failed, 'db_journal'):
        test_logger.info(f"Failed mode - Button enabled: {main_window_failed.db_journal.isEnabled()}")
        test_logger.info(f"Failed mode - Button text: {main_window_failed.db_journal.text()}")
        test_logger.info(f"Failed mode - Button tooltip: {main_window_failed.db_journal.toolTip()}")
    else:
        test_logger.info("Failed mode - db_journal button not available (journal creation failed)")
    main_window_failed.close()
    
    # Автоматически закрываем все окна через 100ms
    def close_all():
        for widget in app.allWidgets():
            if widget.isWindow():
                widget.close()
        app.quit()
    
    QTimer.singleShot(100, close_all)
    app.processEvents()
    
    test_logger.info("\n=== Test completed ===")
