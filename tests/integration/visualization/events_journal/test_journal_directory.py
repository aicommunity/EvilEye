#!/usr/bin/env python3

import sys
import os
def test_journal_directory_behavior(journal_test_logger):
    """Test journal behavior with different directory scenarios"""
    
    journal_test_logger.info("=== Testing Journal Directory Behavior ===")
    
    # Test 1: Directory exists
    journal_test_logger.info("\n1. Directory exists (EvilEyeData):")
    if os.path.exists('EvilEyeData'):
        journal_test_logger.info("   ✅ EvilEyeData directory exists")
        journal_test_logger.info("   ✅ Journal should be created")
        journal_test_logger.info("   ✅ Button should be enabled")
    else:
        journal_test_logger.info("   ❌ EvilEyeData directory does not exist")
        journal_test_logger.info("   ❌ Journal should not be created")
        journal_test_logger.info("   ❌ Button should be disabled")
    
    # Test 2: Non-existent directory
    test_dir = '/non/existent/path'
    journal_test_logger.info(f"\n2. Non-existent directory ({test_dir}):")
    if os.path.exists(test_dir):
        journal_test_logger.info("   ❌ Directory exists (unexpected)")
    else:
        journal_test_logger.info("   ✅ Directory does not exist")
        journal_test_logger.info("   ✅ Journal should not be created")
        journal_test_logger.info("   ✅ Button should be disabled")
    
    # Test 3: Check current config
    journal_test_logger.info("\n3. Current config analysis:")
    try:
        import json
        with open('configs/pipeline_capture.json', 'r') as f:
            config = json.load(f)
        
        use_database = config.get('controller', {}).get('use_database', True)
        image_dir = config.get('database', {}).get('image_dir', 'EvilEyeData')
        
        journal_test_logger.info(f"   use_database: {use_database}")
        journal_test_logger.info(f"   image_dir: {image_dir}")
        journal_test_logger.info(f"   image_dir exists: {os.path.exists(image_dir)}")
        
        if not use_database:
            if os.path.exists(image_dir):
                journal_test_logger.info("   ✅ JSON journal should work")
            else:
                journal_test_logger.info("   ❌ JSON journal should be disabled")
        else:
            journal_test_logger.info("   ℹ️  Database journal should be used")
            
    except Exception as e:
        journal_test_logger.info(f"   ❌ Error reading config: {e}")
    
    journal_test_logger.info("\n=== Expected behavior ===")
    journal_test_logger.info("1. use_database=true: Always try to create DB journal")
    journal_test_logger.info("2. use_database=false + directory exists: Create JSON journal")
    journal_test_logger.info("3. use_database=false + directory missing: Disable journal button")
    
    journal_test_logger.info("\n=== Test completed ===")
