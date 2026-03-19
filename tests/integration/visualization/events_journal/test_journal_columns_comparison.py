#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_journal_columns_comparison(qapp):
    """Test that Events Journal columns match Objects Journal (database) structure"""
    
    test_logger.info("=== Test Events Journal vs Objects Journal Columns Comparison ===")
    
    try:
        from evileye.visualization_modules.events_journal_json import EventsJournalJson
        from evileye.visualization_modules.handler_journal_view import HandlerJournal
        import datetime
        import json
        
        # Use QApplication from fixture
        app = qapp
        
        # Expected column order (from database Objects Journal)
        expected_headers = ['Time', 'Event', 'Information', 'Source', 'Time lost', 'Preview', 'Lost preview']
        
        # Test 1: Check Events Journal structure
        test_logger.info("\n1. Testing Events Journal structure:")
        base_dir = 'EvilEyeData'
        today = datetime.date.today().strftime('%Y_%m_%d')
        test_date_dir = os.path.join(base_dir, today)
        os.makedirs(test_date_dir, exist_ok=True)
        
        # Create minimal test data
        test_data = {
            "metadata": {"version": "1.0", "created": datetime.datetime.now().isoformat()},
            "events": [
                {
                    "event_type": "attr_found",
                    "ts": datetime.datetime.now().isoformat(),
                    "source_id": 0,
                    "source_name": "TestCamera",
                    "object_id": 1,
                    "class_name": "person",
                    "event_name": "test",
                    "date_folder": today
                }
            ]
        }
        
        attr_path = os.path.join(test_date_dir, 'attribute_events.json')
        with open(attr_path, 'w') as f:
            json.dump(test_data, f, indent=2)
        
        events_journal = EventsJournalJson(base_dir)
        test_logger.info("✅ Created EventsJournalJson widget")
        
        # Get Events Journal headers
        events_headers = []
        for i in range(events_journal.table.columnCount()):
            header_item = events_journal.table.horizontalHeaderItem(i)
            if header_item:
                events_headers.append(header_item.text())
            else:
                events_headers.append("")
        
        test_logger.info(f"📋 Events Journal headers: {events_headers}")
        
        # Test 2: Check Objects Journal (database) structure
        test_logger.info("\n2. Testing Objects Journal (database) structure:")
        
        # Get headers from HandlerJournal model
        # Note: HandlerJournal uses QSqlQueryModel, so we check the model headers
        objects_headers = []
        
        # Try to create HandlerJournal if database is available
        try:
            # This requires database connection, so we'll check the code structure instead
            # Read the handler_journal_view.py to get expected headers
            handler_file = 'evileye/visualization_modules/handler_journal_view.py'
            if os.path.exists(handler_file):
                with open(handler_file, 'r') as f:
                    content = f.read()
                    # Extract header definitions from setHeaderData calls
                    import re
                    # Find all setHeaderData calls
                    header_matches = re.findall(r"setHeaderData\((\d+).*?self\.tr\('([^']+)'\)", content)
                    if header_matches:
                        # Sort by column index
                        header_matches.sort(key=lambda x: int(x[0]))
                        objects_headers = [h[1] for h in header_matches]
                        test_logger.info(f"📋 Objects Journal (database) headers from code: {objects_headers}")
        except Exception as e:
            test_logger.warning(f"⚠️  Could not read Objects Journal headers from code: {e}")
            # Use expected headers as fallback
            objects_headers = expected_headers
        
        # If we couldn't get headers from code, use expected headers
        if not objects_headers:
            objects_headers = expected_headers
            test_logger.info(f"📋 Using expected Objects Journal headers: {objects_headers}")
        
        # Test 3: Compare structures
        test_logger.info("\n3. Comparing column structures:")
        
        # Check column count
        events_count = events_journal.table.columnCount()
        objects_count = len(objects_headers)
        
        test_logger.info(f"📊 Events Journal column count: {events_count}")
        test_logger.info(f"📊 Objects Journal column count: {objects_count}")
        
        if events_count != objects_count:
            test_logger.error(f"❌ Column count mismatch: Events={events_count}, Objects={objects_count}")
            assert False, f"Column count mismatch: Events={events_count}, Objects={objects_count}"
        else:
            test_logger.info("✅ Column counts match")
        
        # Check column order
        if events_headers == objects_headers:
            test_logger.info("✅ Column headers match exactly")
            for i, header in enumerate(events_headers):
                test_logger.info(f"   Column {i}: {header} (both journals)")
        else:
            test_logger.error("❌ Column headers don't match")
            test_logger.error(f"   Events Journal: {events_headers}")
            test_logger.error(f"   Objects Journal: {objects_headers}")
            
            # Check which columns differ
            for i in range(min(len(events_headers), len(objects_headers))):
                if events_headers[i] != objects_headers[i]:
                    test_logger.error(f"   Column {i} mismatch: Events='{events_headers[i]}', Objects='{objects_headers[i]}'")
            
            assert False, f"Column headers mismatch. Events: {events_headers}, Objects: {objects_headers}"
        
        # Check against expected headers
        if events_headers == expected_headers:
            test_logger.info("✅ Both journals match expected structure")
        else:
            test_logger.error(f"❌ Headers don't match expected: {expected_headers}")
            assert False, f"Headers don't match expected: {expected_headers}"
        
        # Test 4: Check specific column positions
        test_logger.info("\n4. Checking specific column positions:")
        
        column_checks = {
            'Time': 0,
            'Event': 1,
            'Information': 2,
            'Source': 3,
            'Time lost': 4,
            'Preview': 5,
            'Lost preview': 6
        }
        
        all_correct = True
        for col_name, expected_index in column_checks.items():
            if col_name in events_headers:
                actual_index = events_headers.index(col_name)
                if actual_index == expected_index:
                    test_logger.info(f"   ✅ '{col_name}' at correct position {expected_index}")
                else:
                    test_logger.error(f"   ❌ '{col_name}' at wrong position: {actual_index}, expected {expected_index}")
                    all_correct = False
            else:
                test_logger.error(f"   ❌ '{col_name}' not found in Events Journal")
                all_correct = False
        
        if not all_correct:
            assert False, "Some columns are at wrong positions"
        
        # Test 5: Verify "Event Details" is not present
        test_logger.info("\n5. Verifying 'Event Details' column is removed:")
        if "Event Details" in events_headers:
            test_logger.error("❌ 'Event Details' column still present in Events Journal")
            assert False, "'Event Details' column should not be present"
        else:
            test_logger.info("✅ 'Event Details' column correctly removed from Events Journal")
        
        # Test 6: Verify "Source" column is present
        test_logger.info("\n6. Verifying 'Source' column is present:")
        if "Source" in events_headers:
            source_index = events_headers.index("Source")
            test_logger.info(f"✅ 'Source' column found at index {source_index}")
            if source_index != 3:
                test_logger.error(f"❌ 'Source' column at wrong index: {source_index}, expected 3")
                assert False, f"'Source' column at wrong index: {source_index}, expected 3"
        else:
            test_logger.error("❌ 'Source' column not found in Events Journal")
            assert False, "'Source' column not found"
        
        # Cleanup
        #
        # NOTE: pytest-qt's `qapp` fixture manages QApplication lifetime.
        # Calling `app.quit()` (and then processing events) can intermittently crash
        # native Qt plugins in headless/CI environments.
        if hasattr(events_journal, 'update_timer'):
            try:
                events_journal.update_timer.stop()
            except Exception:
                pass
        try:
            events_journal.close()
        except Exception:
            pass
        if hasattr(events_journal, 'ds') and events_journal.ds:
            try:
                events_journal.ds.close()
            except Exception:
                pass
        
        test_logger.info("\n✅ Journal columns comparison test completed successfully")
        test_logger.info("\n📋 Summary:")
        test_logger.info("   ✅ Events Journal and Objects Journal have same column count (7)")
        test_logger.info("   ✅ Column order is identical: Time, Event, Information, Source, Time lost, Preview, Lost preview")
        test_logger.info("   ✅ All columns at correct positions")
        test_logger.info("   ✅ 'Event Details' column removed from Events Journal")
        test_logger.info("   ✅ 'Source' column present at index 3 in both journals")
        
    except Exception as e:
        test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        raise
