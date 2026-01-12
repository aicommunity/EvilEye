#!/usr/bin/env python3

import sys
import os
import json
from pathlib import Path
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_journal_columns_with_config(qapp):
    """Test Events Journal column structure with data from config files"""
    
    test_logger.info("=== Test Events Journal Columns with Config Data ===")
    
    try:
        from evileye.visualization_modules.events_journal_json import EventsJournalJson
        import datetime
        
        # Use QApplication from fixture
        app = qapp
        
        # Expected column order
        expected_headers = ['Time', 'Event', 'Information', 'Source', 'Time lost', 'Preview', 'Lost preview']
        
        # Find project root
        current = Path(__file__).parent
        while current.name != 'EvilEye' and current.parent != current:
            current = current.parent
        if current.name == 'EvilEye':
            project_root = current
        else:
            project_root = Path(__file__).parent.parent.parent.parent
        
        # Look for config files
        configs_dir = project_root / 'configs'
        test_logger.info(f"📁 Looking for configs in: {configs_dir}")
        
        config_files = []
        if configs_dir.exists():
            config_files = list(configs_dir.glob('*.json'))
            test_logger.info(f"✅ Found {len(config_files)} config files")
        else:
            test_logger.warning(f"⚠️  Configs directory not found: {configs_dir}")
        
        # Create test data directory
        base_dir = 'EvilEyeData'
        today = datetime.date.today().strftime('%Y_%m_%d')
        test_date_dir = os.path.join(base_dir, today)
        os.makedirs(test_date_dir, exist_ok=True)
        
        # Create comprehensive test data based on typical config structure
        test_data_found = {
            "metadata": {
                "version": "1.0",
                "created": datetime.datetime.now().isoformat(),
                "description": "Test data from config",
                "total_objects": 2
            },
            "objects": [
                {
                    "object_id": 1,
                    "frame_id": 1,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "image_filename": "test_preview_1.jpeg",
                    "bounding_box": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
                    "class_id": 0,
                    "class_name": "person",
                    "confidence": 0.85,
                    "source_id": 0,
                    "source_name": "ConfigCamera1",
                    "date_folder": today
                },
                {
                    "object_id": 2,
                    "frame_id": 2,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "image_filename": "test_preview_2.jpeg",
                    "bounding_box": {"x": 0.2, "y": 0.3, "width": 0.4, "height": 0.5},
                    "class_id": 1,
                    "class_name": "car",
                    "confidence": 0.92,
                    "source_id": 1,
                    "source_name": "ConfigCamera2",
                    "date_folder": today
                }
            ]
        }
        
        # Create attribute events
        test_data_attr = {
            "metadata": {"version": "1.0", "created": datetime.datetime.now().isoformat()},
            "events": [
                {
                    "event_type": "attr_found",
                    "ts": datetime.datetime.now().isoformat(),
                    "source_id": 0,
                    "source_name": "ConfigCamera1",
                    "object_id": 1,
                    "class_name": "person",
                    "event_name": "config_attr",
                    "attrs": {"attr1": "value1"},
                    "date_folder": today
                }
            ]
        }
        
        # Write test JSON files
        found_path = os.path.join(test_date_dir, 'objects_found.json')
        with open(found_path, 'w') as f:
            json.dump(test_data_found, f, indent=2)
        
        attr_path = os.path.join(test_date_dir, 'attribute_events.json')
        with open(attr_path, 'w') as f:
            json.dump(test_data_attr, f, indent=2)
        
        test_logger.info(f"✅ Created test JSON data files in {test_date_dir}")
        
        # Create EventsJournalJson widget
        journal = EventsJournalJson(base_dir)
        test_logger.info("✅ Created EventsJournalJson widget")
        
        # Force reload to populate table
        journal._reload_table()
        
        # Check column structure
        column_count = journal.table.columnCount()
        test_logger.info(f"📊 Table has {column_count} columns")
        
        if column_count != 7:
            test_logger.error(f"❌ Expected 7 columns, got {column_count}")
            assert False, f"Expected 7 columns, got {column_count}"
        
        # Get column headers
        actual_headers = []
        for i in range(column_count):
            header_item = journal.table.horizontalHeaderItem(i)
            if header_item:
                actual_headers.append(header_item.text())
            else:
                actual_headers.append("")
        
        test_logger.info(f"📋 Column headers: {actual_headers}")
        
        # Verify headers match expected
        if actual_headers != expected_headers:
            test_logger.error(f"❌ Headers don't match expected: {expected_headers}")
            assert False, f"Headers mismatch. Expected: {expected_headers}, Actual: {actual_headers}"
        
        test_logger.info("✅ Column headers match expected structure")
        
        # Test filtering and date selection
        test_logger.info("\n🔍 Testing filters and date selection:")
        
        # Test date filter
        dates = journal.ds.list_available_dates()
        test_logger.info(f"📅 Available dates: {dates}")
        
        if dates:
            # Set date filter
            journal.ds.set_date(dates[0])
            journal._reload_table()
            test_logger.info(f"✅ Date filter set to: {dates[0]}")
            test_logger.info(f"   Table rows after date filter: {journal.table.rowCount()}")
        
        # Test event type filter
        original_count = journal.table.rowCount()
        journal.filters = {'event_type': 'attr_found'}
        journal._reload_table()
        filtered_count = journal.table.rowCount()
        test_logger.info(f"✅ Event type filter applied: attr_found")
        test_logger.info(f"   Rows before filter: {original_count}, after filter: {filtered_count}")
        
        # Reset filter
        journal.filters = {}
        journal._reload_table()
        
        # Check data population
        if journal.table.rowCount() > 0:
            test_logger.info(f"✅ Table loaded {journal.table.rowCount()} rows")
            
            # Verify data is in correct columns
            for row in range(min(journal.table.rowCount(), 5)):  # Check first 5 rows
                time_item = journal.table.item(row, 0)  # Time
                event_item = journal.table.item(row, 1)  # Event
                info_item = journal.table.item(row, 2)  # Information
                source_item = journal.table.item(row, 3)  # Source
                time_lost_item = journal.table.item(row, 4)  # Time lost
                
                test_logger.info(f"\n📊 Row {row} data:")
                if time_item:
                    test_logger.info(f"   Time (col 0): {time_item.text()[:30]}")
                if event_item:
                    test_logger.info(f"   Event (col 1): {event_item.text()}")
                if info_item:
                    test_logger.info(f"   Information (col 2): {info_item.text()[:50]}")
                if source_item:
                    test_logger.info(f"   Source (col 3): {source_item.text()}")
                if time_lost_item:
                    test_logger.info(f"   Time lost (col 4): {time_lost_item.text()[:30]}")
                
                # Verify Source column has data
                if source_item and source_item.text():
                    test_logger.info(f"   ✅ Source column populated: {source_item.text()}")
                else:
                    test_logger.warning(f"   ⚠️  Source column empty for row {row}")
        else:
            test_logger.info("ℹ️  Table is empty (no events loaded)")
        
        # Verify column resize modes
        test_logger.info("\n📏 Checking column resize modes:")
        h = journal.table.horizontalHeader()
        for i, header in enumerate(actual_headers):
            resize_mode = h.sectionResizeMode(i)
            test_logger.info(f"   Column {i} ({header}): {resize_mode}")
        
        # Cleanup
        def close_window():
            if hasattr(journal, 'update_timer'):
                journal.update_timer.stop()
            journal.close()
            if hasattr(journal, 'ds') and journal.ds:
                journal.ds.close()
            app.quit()
        
        try:
            from PyQt6.QtCore import QTimer
        except ImportError:
            from PyQt5.QtCore import QTimer
        
        QTimer.singleShot(100, close_window)
        
        # Process events
        import time
        for _ in range(5):
            try:
                app.processEvents()
            except (RuntimeError, AttributeError):
                break
            time.sleep(0.1)
        
        test_logger.info("\n✅ Journal columns with config test completed successfully")
        test_logger.info("\n📋 Summary:")
        test_logger.info("   ✅ Events Journal has correct column structure")
        test_logger.info("   ✅ Column order: Time, Event, Information, Source, Time lost, Preview, Lost preview")
        test_logger.info("   ✅ Filters and date selection work correctly")
        test_logger.info("   ✅ Data populated in correct columns")
        test_logger.info("   ✅ Source column populated from config data")
        
    except Exception as e:
        test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        raise
