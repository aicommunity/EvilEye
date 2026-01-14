#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_journal_filters():
    """Test journal filtering"""
    
    test_logger.info("=== Journal Filtering Test ===")
    
    try:
        from evileye.visualization_modules.journal_data_source_json import JsonLabelJournalDataSource
        
        ds = JsonLabelJournalDataSource('EvilEyeData')
        
        # Test different filters
        test_logger.info("\n1. All Events:")
        all_events = ds.fetch(0, 5, {}, [])
        test_logger.info(f"   Total: {len(all_events)}")
        for ev in all_events:
            test_logger.info(f"     {ev.get('event_type')} - {ev.get('ts')} - {ev.get('source_name')}")
        
        test_logger.info("\n2. Found Events Only:")
        found_events = ds.fetch(0, 5, {'event_type': 'found'}, [])
        test_logger.info(f"   Total: {len(found_events)}")
        for ev in found_events:
            test_logger.info(f"     {ev.get('event_type')} - {ev.get('ts')} - {ev.get('source_name')}")
        
        test_logger.info("\n3. Lost Events Only:")
        lost_events = ds.fetch(0, 5, {'event_type': 'lost'}, [])
        test_logger.info(f"   Total: {len(lost_events)}")
        for ev in lost_events:
            test_logger.info(f"     {ev.get('event_type')} - {ev.get('ts')} - {ev.get('source_name')}")
        
        test_logger.info("\n4. Source Filter:")
        source_events = ds.fetch(0, 5, {'source_name': 'Cam5'}, [])
        test_logger.info(f"   Total: {len(source_events)}")
        for ev in source_events:
            test_logger.info(f"     {ev.get('event_type')} - {ev.get('ts')} - {ev.get('source_name')}")
        
        test_logger.info("\n5. Combined Filter:")
        combined_events = ds.fetch(0, 5, {'event_type': 'found', 'source_name': 'Cam5'}, [])
        test_logger.info(f"   Total: {len(combined_events)}")
        for ev in combined_events:
            test_logger.info(f"     {ev.get('event_type')} - {ev.get('ts')} - {ev.get('source_name')}")
        
        ds.close()
        
    except Exception as e:
        test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
