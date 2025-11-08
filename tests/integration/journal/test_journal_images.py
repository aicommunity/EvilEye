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
    
    # Автоматически закрываем окно через 200ms
    def close_window():
        try:
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
    import time
    # Просто ждем, чтобы QTimer.singleShot успел выполниться
    # Не вызываем app.processEvents() в цикле, чтобы избежать segfault
    time.sleep(0.3)  # Увеличиваем задержку
    
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
