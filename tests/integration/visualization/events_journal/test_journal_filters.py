#!/usr/bin/env python3

import sys
import os
def test_journal_filters(journal_test_logger):
    """Test journal filtering"""
    
    journal_test_logger.info("=== Journal Filtering Test ===")
    
    try:
        from evileye.visualization_modules.journal_data_source_json import JsonLabelJournalDataSource
        
        ds = JsonLabelJournalDataSource('EvilEyeData')
        
        # Test different filters
        journal_test_logger.info("\n1. All Events:")
        all_events = ds.fetch(0, 5, {}, [])
        journal_test_logger.info(f"   Total: {len(all_events)}")
        for ev in all_events:
            journal_test_logger.info(f"     {ev.get('event_type')} - {ev.get('ts')} - {ev.get('source_name')}")
        
        journal_test_logger.info("\n2. Found Events Only:")
        found_events = ds.fetch(0, 5, {'event_type': 'found'}, [])
        journal_test_logger.info(f"   Total: {len(found_events)}")
        for ev in found_events:
            journal_test_logger.info(f"     {ev.get('event_type')} - {ev.get('ts')} - {ev.get('source_name')}")
        
        journal_test_logger.info("\n3. Lost Events Only:")
        lost_events = ds.fetch(0, 5, {'event_type': 'lost'}, [])
        journal_test_logger.info(f"   Total: {len(lost_events)}")
        for ev in lost_events:
            journal_test_logger.info(f"     {ev.get('event_type')} - {ev.get('ts')} - {ev.get('source_name')}")
        
        journal_test_logger.info("\n4. Source Filter:")
        source_events = ds.fetch(0, 5, {'source_name': 'Cam5'}, [])
        journal_test_logger.info(f"   Total: {len(source_events)}")
        for ev in source_events:
            journal_test_logger.info(f"     {ev.get('event_type')} - {ev.get('ts')} - {ev.get('source_name')}")
        
        journal_test_logger.info("\n5. Combined Filter:")
        combined_events = ds.fetch(0, 5, {'event_type': 'found', 'source_name': 'Cam5'}, [])
        journal_test_logger.info(f"   Total: {len(combined_events)}")
        for ev in combined_events:
            journal_test_logger.info(f"     {ev.get('event_type')} - {ev.get('ts')} - {ev.get('source_name')}")
        
        ds.close()
        
    except Exception as e:
        journal_test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
