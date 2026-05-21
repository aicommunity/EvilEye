#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_journal_directory_behavior():
    """Test journal behavior with different directory scenarios"""
    
    test_logger.info("=== Testing Journal Directory Behavior ===")
    
    # Test 1: Directory exists
    test_logger.info("\n1. Directory exists (EvilEyeData):")
    if os.path.exists('EvilEyeData'):
        test_logger.info("   ✅ EvilEyeData directory exists")
        test_logger.info("   ✅ Journal should be created")
        test_logger.info("   ✅ Button should be enabled")
    else:
        test_logger.info("   ❌ EvilEyeData directory does not exist")
        test_logger.info("   ❌ Journal should not be created")
        test_logger.info("   ❌ Button should be disabled")
    
    # Test 2: Non-existent directory
    test_dir = '/non/existent/path'
    test_logger.info(f"\n2. Non-existent directory ({test_dir}):")
    if os.path.exists(test_dir):
        test_logger.info("   ❌ Directory exists (unexpected)")
    else:
        test_logger.info("   ✅ Directory does not exist")
        test_logger.info("   ✅ Journal should not be created")
        test_logger.info("   ✅ Button should be disabled")
    
    # Test 3: Check current config
    test_logger.info("\n3. Current config analysis:")
    try:
        import json
        with open('configs/pipeline_capture.json', 'r') as f:
            config = json.load(f)
        
        use_database = config.get('controller', {}).get('use_database', True)
        image_dir = config.get('database', {}).get('image_dir', 'EvilEyeData')
        
        test_logger.info(f"   use_database: {use_database}")
        test_logger.info(f"   image_dir: {image_dir}")
        test_logger.info(f"   image_dir exists: {os.path.exists(image_dir)}")
        
        if not use_database:
            if os.path.exists(image_dir):
                test_logger.info("   ✅ JSON journal should work")
            else:
                test_logger.info("   ❌ JSON journal should be disabled")
        else:
            test_logger.info("   ℹ️  Database journal should be used")
            
    except Exception as e:
        test_logger.info(f"   ❌ Error reading config: {e}")
    
    test_logger.info("\n=== Expected behavior ===")
    test_logger.info("1. use_database=true: Always try to create DB journal")
    test_logger.info("2. use_database=false + directory exists: Create JSON journal")
    test_logger.info("3. use_database=false + directory missing: Disable journal button")
    
    test_logger.info("\n=== Test completed ===")
