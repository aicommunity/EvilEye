#!/usr/bin/env python3

import sys
import os
def test_data_source(journal_test_logger):
    """Test data source functionality"""
    
    journal_test_logger.info("=== Test Data Source ===")
    
    try:
        from evileye.visualization_modules.journal_data_source_json import JsonLabelJournalDataSource
        
        # Create data source
        base_dir = "EvilEyeData"
        ds = JsonLabelJournalDataSource(base_dir)
        
        journal_test_logger.info(f"✅ Data source created with base_dir: {base_dir}")
        
        # Test available dates
        dates = ds.list_available_dates()
        journal_test_logger.info(f"📅 Available dates: {dates}")
        
        # Test fetching data
        if dates:
            # Use first available date
            test_date = dates[0]
            journal_test_logger.info(f"📊 Testing with date: {test_date}")
            
            ds.set_date(test_date)
            data = ds.fetch(0, 10, {}, [])
            journal_test_logger.info(f"📈 Fetched {len(data)} records")
            
            if data:
                journal_test_logger.info("📋 Sample data:")
                for i, record in enumerate(data[:3]):
                    journal_test_logger.info(f"  Record {i+1}: {record}")
            else:
                journal_test_logger.info("❌ No data found")
        else:
            journal_test_logger.info("❌ No dates available")
            
        # Test without date filter
        journal_test_logger.info("\n--- Testing without date filter ---")
        ds.set_date(None)
        data = ds.fetch(0, 10, {}, [])
        journal_test_logger.info(f"📈 Fetched {len(data)} records (no date filter)")
        
        if data:
            journal_test_logger.info("📋 Sample data:")
            for i, record in enumerate(data[:3]):
                journal_test_logger.info(f"  Record {i+1}: {record}")
        else:
            journal_test_logger.info("❌ No data found without date filter")
            
    except Exception as e:
        journal_test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
