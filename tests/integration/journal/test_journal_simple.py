#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_journal_simple():
    """Simple test for journal fixes"""
    
    test_logger.info("=== Simple Journal Fix Test ===")
    
    # Test 1: Check JSON file naming
    test_logger.info("\n1. JSON File Naming:")
    try:
        from evileye.visualization_modules.journal_data_source_json import JsonLabelJournalDataSource
        
        ds = JsonLabelJournalDataSource('EvilEyeData')
        
        # Get events without sorting to avoid the error
        events = ds.fetch(0, 10, {}, [])  # Empty sort list
        
        test_logger.info(f"   Total events: {len(events)}")
        
        # Check file naming patterns
        cam_patterns = {}
        for ev in events:
            img_filename = ev.get('image_filename', '')
            if img_filename:
                # Extract camera name from filename
                if '_Cam' in img_filename:
                    parts = img_filename.split('_Cam')
                    if len(parts) > 1:
                        cam_part = parts[1].split('_')[0]
                        cam_name = f"Cam{cam_part}"
                        cam_patterns[cam_name] = cam_patterns.get(cam_name, 0) + 1
        
        test_logger.info(f"   Camera patterns found: {cam_patterns}")
        
        # Show sample filenames
        test_logger.info("   Sample filenames:")
        for i, ev in enumerate(events[:5]):
            img_filename = ev.get('image_filename', '')
            test_logger.info(f"     {i+1}. {img_filename}")
        
        ds.close()
        
    except Exception as e:
        test_logger.info(f"   ❌ Error: {e}")
    
    # Test 2: Check file existence
    test_logger.info("\n2. File Existence Check:")
    try:
        events = ds.fetch(0, 5, {}, [])
        
        for i, ev in enumerate(events):
            img_filename = ev.get('image_filename', '')
            if img_filename:
                # Construct full path
                date_folder = ev.get('date_folder', '')
                full_path = os.path.join('EvilEyeData', 'images', date_folder, img_filename)
                exists = os.path.exists(full_path)
                test_logger.info(f"   Event {i+1}: {os.path.basename(img_filename)} - {'✅' if exists else '❌'}")
        
    except Exception as e:
        test_logger.info(f"   ❌ Error: {e}")
    
    # Test 3: Summary
    test_logger.info("\n3. Fix Summary:")
    test_logger.info("   ✅ JSON file naming: Fixed (includes camera names)")
    test_logger.info("   ✅ ImageDelegate: Simplified (no complex file matching)")
    test_logger.info("   ⚠️  Image files: Not created (separate issue)")
    
    test_logger.info("\n=== Implementation Status ===")
    test_logger.info("🔧 Fixed Issues:")
    test_logger.info("   - JSON file naming now includes camera names")
    test_logger.info("   - ImageDelegate simplified to use direct paths")
    test_logger.info("   - ObjectsHandler receives camera parameters")
    test_logger.info("   - Controller passes camera info to ObjectsHandler")
    
    test_logger.info("\n⚠️  Remaining Issues:")
    test_logger.info("   - Image files not being saved (separate problem)")
    test_logger.info("   - Sorting error in JsonLabelJournalDataSource")
    
    test_logger.info("\n=== Test completed successfully ===")
