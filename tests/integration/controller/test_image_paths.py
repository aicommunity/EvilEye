#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_image_paths():
    """Test image paths in journal"""
    
    test_logger.info("=== Test Image Paths ===")
    
    try:
        from evileye.visualization_modules.journal_data_source_json import JsonLabelJournalDataSource
        
        ds = JsonLabelJournalDataSource('EvilEyeData')
        
        # Get sample data
        events = ds.fetch(0, 5, {}, [])
        
        test_logger.info(f"\n📊 Image Paths Test:")
        for i, ev in enumerate(events):
            test_logger.info(f"   Event {i+1}:")
            test_logger.info(f"     Type: {ev.get('event_type')}")
            test_logger.info(f"     Object ID: {ev.get('object_id')}")
            test_logger.info(f"     Image filename: {ev.get('image_filename')}")
            test_logger.info(f"     Date folder: {ev.get('date_folder')}")
            
            # Test full path
            if ev.get('image_filename') and ev.get('date_folder'):
                full_path = os.path.join('EvilEyeData', 'images', ev.get('date_folder'), ev.get('image_filename'))
                exists = os.path.exists(full_path)
                test_logger.info(f"     Full path: {full_path}")
                test_logger.info(f"     Exists: {exists}")
                
                # Check if directory exists
                dir_path = os.path.join('EvilEyeData', 'images', ev.get('date_folder'))
                dir_exists = os.path.exists(dir_path)
                test_logger.info(f"     Directory exists: {dir_exists}")
                
                if dir_exists:
                    # List files in directory
                    try:
                        files = os.listdir(dir_path)
                        test_logger.info(f"     Files in directory: {len(files)}")
                        if len(files) > 0:
                            test_logger.info(f"     Sample files: {files[:3]}")
                    except Exception as e:
                        test_logger.info(f"     Error listing directory: {e}")
        
        ds.close()
        
    except Exception as e:
        test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
