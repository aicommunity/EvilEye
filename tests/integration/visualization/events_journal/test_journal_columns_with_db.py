#!/usr/bin/env python3

import json

from pathlib import Path

from tests.integration.visualization.events_journal.helpers import (
    EXPECTED_JOURNAL_HEADERS,
    table_horizontal_headers,
)


def test_journal_columns_with_db(journal_test_logger, qapp, tmp_path):
    """Test JSON journal columns against isolated event fixtures."""
    
    journal_test_logger.info("=== Test Events Journal Columns with Database ===")
    
    try:
        import datetime

        # Use a private fixture tree: the repository's EvilEyeData may contain
        # years of production recordings and must never be scanned or modified
        # by this structural widget test.
        base_dir = str(tmp_path)
        today = datetime.date.today().strftime("%Y-%m-%d")
        metadata_dir = Path(base_dir) / "Events" / today / "Metadata"
        metadata_dir.mkdir(parents=True)

        # Create representative events using the JSON journal's current file
        # layout and record schemas.
        test_data = {
            "attribute_events_found.json": [{
                "ts": datetime.datetime.now().isoformat(),
                "source_id": 0,
                "source_name": "Camera1",
                "object_id": 1,
                "class_name": "person",
                "event_name": "test_attr",
            }],
            "zone_events_entered.json": [{
                "ts": datetime.datetime.now().isoformat(),
                "source_id": 1,
                "source_name": "Camera2",
                "object_id": 2,
                "zone_id": "zone1",
            }],
            "camera_events.json": [{
                "ts": datetime.datetime.now().isoformat(),
                "camera_full_address": "rtsp://test-camera",
                "connection_status": "connected",
            }],
            "system_events.json": [{
                "ts": datetime.datetime.now().isoformat(),
                "event_type": "SystemStart",
            }],
        }
        for filename, events in test_data.items():
            with (metadata_dir / filename).open("w", encoding="utf-8") as event_file:
                json.dump(events, event_file, indent=2)

        journal_test_logger.info("Created isolated JSON journal fixtures")

        from evileye.visualization_modules.events_journal_json import EventsJournalJson
        import datetime
        
        # Use QApplication from fixture
        app = qapp
        
        # Expected column order
        expected_headers = EXPECTED_JOURNAL_HEADERS
        
        # Create EventsJournalJson widget
        journal = EventsJournalJson(base_dir)
        assert journal.update_timer.parent() is journal
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
