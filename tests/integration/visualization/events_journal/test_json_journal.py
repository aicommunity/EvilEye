#!/usr/bin/env python3

import sys
import os
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt, QTimer
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt, QTimer
    pyqt_version = 5

from evileye.visualization_modules.events_journal_json import EventsJournalJson

def test_json_journal(journal_test_logger, qapp):
    app = qapp
    
    # Test with existing data
    journal = EventsJournalJson('EvilEyeData')
    journal.show()
    
    journal_test_logger.info("JSON Journal test window opened.")
    
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
