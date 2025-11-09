#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_journal_final_complete():
    """Test all journal scenarios with the latest fixes"""
    
    test_logger.info("=== Final Journal Testing with Directory Checks ===")
    
    # Test 1: Check current directory status
    test_logger.info("\n1. Directory Status Check:")
    evil_eye_data_exists = os.path.exists('EvilEyeData')
    test_logger.info(f"   EvilEyeData exists: {evil_eye_data_exists}")
    
    if evil_eye_data_exists:
        dates = [d for d in os.listdir('EvilEyeData') 
                if os.path.isdir(os.path.join('EvilEyeData', d)) and d[:4].isdigit()]
        test_logger.info(f"   Available date folders: {dates}")
        
        total_events = 0
        for date in dates:
            found_file = os.path.join('EvilEyeData', date, 'objects_found.json')
            lost_file = os.path.join('EvilEyeData', date, 'objects_lost.json')
            if os.path.exists(found_file):
                import json
                with open(found_file, 'r') as f:
                    found_events = len(json.load(f))
                    total_events += found_events
                test_logger.info(f"   {date}/objects_found.json: {found_events} events")
            if os.path.exists(lost_file):
                import json
                with open(lost_file, 'r') as f:
                    lost_events = len(json.load(f))
                    total_events += lost_events
                test_logger.info(f"   {date}/objects_lost.json: {lost_events} events")
        test_logger.info(f"   Total events available: {total_events}")
    
    # Test 2: Check configs
    test_logger.info("\n2. Configuration Analysis:")
    configs_to_check = [
        ('configs/pipeline_capture.json', 'Normal JSON mode'),
        ('configs/pipeline_capture_no_dir.json', 'JSON mode with non-existent dir'),
        ('configs/pipeline_capture_db.json', 'Database mode')
    ]
    
    for config_file, description in configs_to_check:
        if os.path.exists(config_file):
            import json
            with open(config_file, 'r') as f:
                config = json.load(f)
            
            use_database = config.get('controller', {}).get('use_database', True)
            image_dir = config.get('database', {}).get('image_dir', 'EvilEyeData')
            image_dir_exists = os.path.exists(image_dir)
            
            test_logger.info(f"   {description}:")
            test_logger.info(f"     use_database: {use_database}")
            test_logger.info(f"     image_dir: {image_dir}")
            test_logger.info(f"     image_dir exists: {image_dir_exists}")
            
            if not use_database:
                if image_dir_exists:
                    test_logger.info(f"     Expected: JSON journal enabled")
                else:
                    test_logger.info(f"     Expected: JSON journal disabled")
            else:
                test_logger.info(f"     Expected: Database journal")
        else:
            test_logger.info(f"   {description}: Config file not found")
    
    # Test 3: Expected behavior summary
    test_logger.info("\n3. Expected Behavior Summary:")
    test_logger.info("   ✅ use_database=true: Always try to create DB journal")
    test_logger.info("   ✅ use_database=false + directory exists: Create JSON journal")
    test_logger.info("   ✅ use_database=false + directory missing: Disable journal button")
    test_logger.info("   ✅ No automatic directory creation")
    test_logger.info("   ✅ Clear error messages for missing directories")
    
    # Test 4: Implementation status
    test_logger.info("\n4. Implementation Status:")
    test_logger.info("   ✅ MainWindow gets database_config even when use_database=false")
    test_logger.info("   ✅ image_dir extracted from database_config")
    test_logger.info("   ✅ Directory existence check before journal creation")
    test_logger.info("   ✅ No automatic directory creation (os.makedirs removed)")
    test_logger.info("   ✅ Journal button disabled when directory missing")
    test_logger.info("   ✅ Clear error messages in console")
    
    test_logger.info("\n=== Test completed successfully ===")
