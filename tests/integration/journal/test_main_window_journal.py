#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt, QTimer
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt, QTimer
    pyqt_version = 5

from evileye.visualization_modules.main_window import MainWindow
from evileye.controller.controller import Controller

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_main_window_journal():
    app = QApplication(sys.argv)
    
    # Create a mock controller with use_database=False
    class MockController:
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
    
    controller = MockController()
    
    # Test config
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
    
    # Create main window
    main_window = MainWindow(controller, 'test_config.json', config, 800, 600)
    main_window.show()
    
    test_logger.info("Main window with JSON journal opened.")
    
    # Автоматически закрываем окно через 100ms
    def close_window():
        # Закрываем главное окно
        main_window.close()
        # Выходим из приложения
        app.quit()
    
    QTimer.singleShot(100, close_window)
    # Даем время на закрытие окна
    import time
    time.sleep(0.2)
    
    # Явно закрываем окно на случай, если таймер не сработал
    try:
        main_window.close()
        # Не вызываем app.quit() здесь, так как он уже вызван в close_window()
    except Exception:
        pass
