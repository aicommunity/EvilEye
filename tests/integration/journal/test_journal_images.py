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

from evileye.visualization_modules.events_journal_json import EventsJournalJson

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_journal_images():
    app = QApplication(sys.argv)
    
    test_logger.info("Testing JSON journal with image display...")
    
    # Test with existing data
    journal = EventsJournalJson('EvilEyeData')
    journal.show()
    
    test_logger.info("JSON Journal window opened with image display.")
    test_logger.info("Available dates:", journal.ds.list_available_dates())
    test_logger.info("Total events:", journal.ds.get_total({}))
    
    # Test image paths
    events = journal.ds.fetch(0, 5, {}, [('ts', 'desc')])
    test_logger.info(f"First 5 events with image paths:")
    for i, ev in enumerate(events):
        img_rel = ev.get('image_filename') or ''
        date_folder = ev.get('date_folder') or ''
        img_path = os.path.join('EvilEyeData', 'images', date_folder, img_rel)
        bbox = ev.get('bounding_box') or ''
        
        test_logger.info(f"  Event {i+1}:")
        test_logger.info(f"    Type: {ev.get('event_type')}")
        test_logger.info(f"    Class: {ev.get('class_name')}")
        test_logger.info(f"    Image path: {img_path}")
        test_logger.info(f"    Image exists: {os.path.exists(img_path)}")
        test_logger.info(f"    BBox: {bbox}")
    
    # Автоматически закрываем окно через 100ms
    def close_window():
        journal.close()
        journal.ds.close()
        app.quit()
    
    QTimer.singleShot(100, close_window)
    app.processEvents()
