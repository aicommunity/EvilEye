#!/usr/bin/env python3

def test_journal_simple_gui(journal_test_logger, qapp):
    """Populate a simple table from JsonLabelJournalDataSource (no EventsJournalJson window)."""
    try:
        from PyQt6.QtWidgets import (
            QMainWindow,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )
        from PyQt6.QtCore import QTimer
    except ImportError:
        from PyQt5.QtWidgets import (
            QMainWindow,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )
        from PyQt5.QtCore import QTimer

    from evileye.visualization_modules.journal_data_source_json import JsonLabelJournalDataSource

    app = qapp
    window = QMainWindow()
    window.setWindowTitle("Journal Data Test")
    window.setGeometry(100, 100, 800, 600)

    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    layout = QVBoxLayout(central_widget)

    table = QTableWidget(0, 6)
    table.setHorizontalHeaderLabels(
        ["Type", "Time", "Source", "Class", "Image", "BBox"]
    )
    layout.addWidget(table)

    ds = JsonLabelJournalDataSource("EvilEyeData")
    events = ds.fetch(0, 10, {}, [])
    journal_test_logger.info("Loaded %s events", len(events))

    table.setRowCount(len(events))
    for r, ev in enumerate(events):
        table.setItem(r, 0, QTableWidgetItem(ev.get("event_type", "")))
        table.setItem(r, 1, QTableWidgetItem(str(ev.get("ts", ""))))
        table.setItem(
            r,
            2,
            QTableWidgetItem(str(ev.get("source_name", ev.get("source_id", "")))),
        )
        table.setItem(
            r,
            3,
            QTableWidgetItem(str(ev.get("class_name", ev.get("class_id", "")))),
        )
        table.setItem(r, 4, QTableWidgetItem(str(ev.get("image_filename", ""))))
        table.setItem(r, 5, QTableWidgetItem(str(ev.get("bounding_box", ""))))

    window.show()

    def close_window():
        window.close()
        ds.close()
        app.quit()

    QTimer.singleShot(100, close_window)
    import time

    time.sleep(0.2)
    try:
        window.close()
        ds.close()
    except Exception:
        pass
