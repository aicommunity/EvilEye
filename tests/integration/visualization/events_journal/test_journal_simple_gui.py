#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_journal_simple_gui():
    """Test journal GUI with simple data display"""
    
    test_logger.info("=== Journal Simple GUI Test ===")
    
    try:
        try:
            from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QTableWidget, QTableWidgetItem
            from PyQt6.QtCore import QTimer
        except ImportError:
            from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QTableWidget, QTableWidgetItem
            from PyQt5.QtCore import QTimer
        
        from evileye.visualization_modules.journal_data_source_json import JsonLabelJournalDataSource
        
        # Create QApplication
        app = QApplication(sys.argv)
        
        # Create main window
        window = QMainWindow()
        window.setWindowTitle('Journal Data Test')
        window.setGeometry(100, 100, 800, 600)
        
        # Create central widget
        central_widget = QWidget()
        window.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Create table
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(['Type', 'Time', 'Source', 'Class', 'Image', 'BBox'])
        layout.addWidget(table)
        
        # Load data
        ds = JsonLabelJournalDataSource('EvilEyeData')
        events = ds.fetch(0, 10, {}, [])  # No sorting
        
        test_logger.info(f"Loaded {len(events)} events")
        
        # Populate table
        table.setRowCount(len(events))
        for r, ev in enumerate(events):
            # Type column
            type_item = QTableWidgetItem(ev.get('event_type', ''))
            table.setItem(r, 0, type_item)
            
            # Time column
            time_item = QTableWidgetItem(str(ev.get('ts', '')))
            table.setItem(r, 1, time_item)
            
            # Source column
            source_item = QTableWidgetItem(str(ev.get('source_name', ev.get('source_id', ''))))
            table.setItem(r, 2, source_item)
            
            # Class column
            class_item = QTableWidgetItem(str(ev.get('class_name', ev.get('class_id', ''))))
            table.setItem(r, 3, class_item)
            
            # Image column
            img_item = QTableWidgetItem(str(ev.get('image_filename', '')))
            table.setItem(r, 4, img_item)
            
            # BBox column
            bbox_item = QTableWidgetItem(str(ev.get('bounding_box', '')))
            table.setItem(r, 5, bbox_item)
            
            test_logger.info(f"Row {r}: Type={ev.get('event_type')}, Time={ev.get('ts')}, Source={ev.get('source_name')}")
        
        # Show window
        window.show()
        
        test_logger.info("✅ Table populated with data")
        test_logger.info("📋 Check the table to verify data is correct")
        
        # Автоматически закрываем окно через 100ms
        def close_window():
            # Закрываем окно
            window.close()
            # Закрываем data source
            if ds:
                ds.close()
            # Выходим из приложения
            app.quit()
        
        QTimer.singleShot(100, close_window)
        # Даем время на закрытие окна
        import time
        time.sleep(0.2)
        
        # Явно закрываем окно на случай, если таймер не сработал
        try:
            window.close()
            if ds:
                ds.close()
            app.quit()
        except Exception:
            pass
        
    except Exception as e:
        test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
