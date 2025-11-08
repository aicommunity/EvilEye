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

def test_json_journal():
    app = QApplication(sys.argv)
    
    # Test with existing data
    journal = EventsJournalJson('EvilEyeData')
    journal.show()
    
    test_logger.info("JSON Journal test window opened.")
    
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
        # Не вызываем app.quit() здесь, так как он уже вызван в close_window()
    except Exception:
        pass
