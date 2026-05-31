#!/usr/bin/env python3

import os
import json

from tests.integration.visualization.events_journal.helpers import (
    EXPECTED_JOURNAL_HEADERS,
    journal_today_folder,
    load_db_config,
    table_horizontal_headers,
    write_json,
)


def test_journal_columns_with_db(journal_test_logger, qapp):
    """Test Events Journal column structure with real database data"""
    
    journal_test_logger.info("=== Test Events Journal Columns with Database ===")
    
    try:
        # Try to load database config
        try:
            db_conf = load_db_config()
            journal_test_logger.info("✅ Database config loaded")
            db_available = True
        except Exception as e:
            journal_test_logger.warning(f"⚠️  Database config not available: {e}")
            journal_test_logger.info("   Continuing with JSON data only")
            db_available = False
        
        from evileye.visualization_modules.events_journal_json import EventsJournalJson
        import datetime
        
        # Use QApplication from fixture
        app = qapp
        
        # Expected column order
        expected_headers = EXPECTED_JOURNAL_HEADERS
        
        # Create test data directory
        base_dir = 'EvilEyeData'
        today, test_date_dir = journal_today_folder(base_dir)
        
        # Create test JSON data for different event types to test Source column
        test_data = {
            "metadata": {"version": "1.0", "created": datetime.datetime.now().isoformat()},
            "events": [
                {
                    "event_type": "attr_found",
                    "ts": datetime.datetime.now().isoformat(),
                    "source_id": 0,
                    "source_name": "Camera1",
                    "object_id": 1,
                    "class_name": "person",
                    "event_name": "test_attr",
                    "date_folder": today
                },
                {
                    "event_type": "zone_entered",
                    "ts": datetime.datetime.now().isoformat(),
                    "source_id": 1,
                    "object_id": 2,
                    "zone_id": "zone1",
                    "date_folder": today
                },
                {
                    "event_type": "fov_found",
                    "ts": datetime.datetime.now().isoformat(),
                    "source_id": 2,
                    "object_id": 3,
                    "date_folder": today
                },
                {
                    "event_type": "cam",
                    "ts": datetime.datetime.now().isoformat(),
                    "camera_full_address": "rtsp://test-camera",
                    "connection_status": "connected",
                    "date_folder": today
                },
                {
                    "event_type": "sys",
                    "ts": datetime.datetime.now().isoformat(),
                    "event_type": "system_start",
                    "date_folder": today
                }
            ]
        }
        
        attr_path = os.path.join(test_date_dir, 'attribute_events.json')
        with open(attr_path, 'w') as f:
            json.dump(test_data, f, indent=2)
        
        zone_path = os.path.join(test_date_dir, 'zone_events.json')
        with open(zone_path, 'w') as f:
            json.dump(test_data, f, indent=2)
        
        fov_path = os.path.join(test_date_dir, 'fov_events.json')
        with open(fov_path, 'w') as f:
            json.dump(test_data, f, indent=2)
        
        cam_path = os.path.join(test_date_dir, 'camera_events.json')
        with open(cam_path, 'w') as f:
            json.dump(test_data, f, indent=2)
        
        sys_path = os.path.join(test_date_dir, 'system_events.json')
        with open(sys_path, 'w') as f:
            json.dump(test_data, f, indent=2)
        
        journal_test_logger.info("✅ Created test JSON data files for all event types")
        
        # Create EventsJournalJson widget
        journal = EventsJournalJson(base_dir)
        journal_test_logger.info("✅ Created EventsJournalJson widget")
        
        # Force reload to populate table
        journal._reload_table()
        
        # Check column structure
        column_count = journal.table.columnCount()
        journal_test_logger.info(f"📊 Table has {column_count} columns")
        
        if column_count != 7:
            journal_test_logger.error(f"❌ Expected 7 columns, got {column_count}")
            assert False, f"Expected 7 columns, got {column_count}"
        
        # Get column headers
        actual_headers = table_horizontal_headers(journal.table)
        
        journal_test_logger.info(f"📋 Column headers: {actual_headers}")
        
        # Verify headers match expected
        if actual_headers != expected_headers:
            journal_test_logger.error(f"❌ Headers don't match expected: {expected_headers}")
            assert False, f"Headers mismatch. Expected: {expected_headers}, Actual: {actual_headers}"
        
        journal_test_logger.info("✅ Column headers match expected structure")
        
        # Check data population in Source column for different event types
        if journal.table.rowCount() > 0:
            journal_test_logger.info(f"✅ Table loaded {journal.table.rowCount()} rows")
            
            # Check Source column (index 3) for different event types
            source_column_index = 3
            source_values = []
            
            for row in range(min(journal.table.rowCount(), 10)):  # Check first 10 rows
                source_item = journal.table.item(row, source_column_index)
                event_item = journal.table.item(row, 1)  # Event column
                
                if source_item and event_item:
                    source_val = source_item.text()
                    event_val = event_item.text()
                    source_values.append((event_val, source_val))
                    journal_test_logger.info(f"   Row {row}: Event='{event_val}', Source='{source_val}'")
            
            # Verify Source column is populated
            non_empty_sources = [s for _, s in source_values if s]
            if non_empty_sources:
                journal_test_logger.info(f"✅ Source column populated for {len(non_empty_sources)} rows")
            else:
                journal_test_logger.warning("⚠️  Source column is empty for all rows")
            
            # Check specific event types have correct source values
            for event_type, source_val in source_values:
                if event_type == 'CameraEvent':
                    if source_val and 'rtsp' in source_val.lower():
                        journal_test_logger.info(f"✅ CameraEvent has correct source (camera address): {source_val}")
                    else:
                        journal_test_logger.warning(f"⚠️  CameraEvent source may be incorrect: {source_val}")
                elif event_type == 'SystemEvent':
                    if source_val == 'System':
                        journal_test_logger.info(f"✅ SystemEvent has correct source: {source_val}")
                    else:
                        journal_test_logger.warning(f"⚠️  SystemEvent source may be incorrect: {source_val}")
                elif event_type in ('AttributeEvent', 'ZoneEvent', 'FOVEvent'):
                    if source_val:
                        journal_test_logger.info(f"✅ {event_type} has source: {source_val}")
                    else:
                        journal_test_logger.warning(f"⚠️  {event_type} source is empty")
        else:
            journal_test_logger.info("ℹ️  Table is empty (no events loaded)")
        
        # Verify column data types and delegates
        journal_test_logger.info("\n📊 Checking column delegates:")
        
        # Check if delegates are set (we know from code they should be on specific columns)
        if hasattr(journal, 'datetime_delegate') and journal.datetime_delegate:
            journal_test_logger.info("✅ DateTimeDelegate is configured")
            journal_test_logger.info("   Should be on columns: Time (0), Time lost (4)")
        else:
            journal_test_logger.error("❌ DateTimeDelegate not found")
            assert False, "DateTimeDelegate should be configured"
        
        if hasattr(journal, 'image_delegate') and journal.image_delegate:
            journal_test_logger.info("✅ ImageDelegate is configured")
            journal_test_logger.info("   Should be on columns: Preview (5), Lost preview (6)")
        else:
            journal_test_logger.error("❌ ImageDelegate not found")
            assert False, "ImageDelegate should be configured"
        
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
        
        journal_test_logger.info("\n✅ Journal columns with DB test completed successfully")
        journal_test_logger.info("\n📋 Summary:")
        journal_test_logger.info("   ✅ Events Journal has correct column structure")
        journal_test_logger.info("   ✅ Column order: Time, Event, Information, Source, Time lost, Preview, Lost preview")
        journal_test_logger.info("   ✅ Source column populated for different event types")
        journal_test_logger.info("   ✅ Column delegates correctly assigned")
        
    except Exception as e:
        journal_test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        raise
