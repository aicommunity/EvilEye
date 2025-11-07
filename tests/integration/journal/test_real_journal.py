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

def test_real_journal():
    app = QApplication(sys.argv)
    
    test_logger.info("Testing JSON journal with real data...")
    
    # Test with existing data
    journal = EventsJournalJson('EvilEyeData')
    journal.show()
    
    test_logger.info("JSON Journal window opened.")
    test_logger.info("Available dates:", journal.ds.list_available_dates())
    test_logger.info("Total events:", journal.ds.get_total({}))
    
    # Test filtering
    found_events = journal.ds.get_total({'event_type': 'found'})
    lost_events = journal.ds.get_total({'event_type': 'lost'})
    test_logger.info(f"Found events: {found_events}")
    test_logger.info(f"Lost events: {lost_events}")
    
    # Test fetching
    events = journal.ds.fetch(0, 10, {}, [('ts', 'desc')])
    test_logger.info(f"First 10 events: {len(events)}")
    for i, ev in enumerate(events[:3]):  # Show first 3
        test_logger.info(f"  Event {i+1}: {ev.get('event_type')} - {ev.get('class_name')} - {ev.get('ts')}")
    
    # Автоматически закрываем окно через 100ms
    def close_window():
        journal.close()
        app.quit()
    
    QTimer.singleShot(100, close_window)
    app.processEvents()
