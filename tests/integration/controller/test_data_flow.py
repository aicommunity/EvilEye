#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_data_flow():
    """Test data flow in the system"""
    
    test_logger.info("=== Test Data Flow ===")
    
    try:
        # Check if objects_handler is being called
        test_logger.info("🔍 Checking if objects_handler is being called...")
        
        # Check if there are any active objects in the system
        from evileye.objects_handler.objects_handler import ObjectsHandler
        
        # Create a simple objects handler
        handler = ObjectsHandler(db_controller=None, db_adapter=None)
        
        test_logger.info(f"✅ ObjectsHandler created")
        test_logger.info(f"📊 Active objects: {len(handler.active_objs.objects)}")
        test_logger.info(f"📊 Lost objects: {len(handler.lost_objs.objects)}")
        
        # Check if labeling manager is initialized
        if hasattr(handler, 'labeling_manager'):
            test_logger.info(f"✅ Labeling manager initialized")
            test_logger.info(f"📊 Found buffer size: {len(handler.labeling_manager.found_buffer)}")
            test_logger.info(f"📊 Lost buffer size: {len(handler.labeling_manager.lost_buffer)}")
        else:
            test_logger.info("❌ Labeling manager not initialized")
            
        # Check if there are any recent files
        import glob
        recent_files = glob.glob("EvilEyeData/images/2025_09_01/detected_frames/*.jpeg")
        test_logger.info(f"📁 Recent detected frames: {len(recent_files)}")
        
        if recent_files:
            test_logger.info("📋 Recent files:")
            for f in recent_files[-3:]:  # Show last 3 files
                test_logger.info(f"  {os.path.basename(f)}")
        
        # Check if objects are being detected but not saved
        test_logger.info("\n🔍 Checking detection results...")
        
        # Try to read the current JSON files
        found_file = "EvilEyeData/images/2025_09_01/objects_found.json"
        lost_file = "EvilEyeData/images/2025_09_01/objects_lost.json"
        
        if os.path.exists(found_file):
            import json
            with open(found_file, 'r') as f:
                found_data = json.load(f)
            test_logger.info(f"📊 Found objects in JSON: {found_data['metadata']['total_objects']}")
        else:
            test_logger.info("❌ Found objects JSON file not found")
            
        if os.path.exists(lost_file):
            import json
            with open(lost_file, 'r') as f:
                lost_data = json.load(f)
            test_logger.info(f"📊 Lost objects in JSON: {lost_data['metadata']['total_objects']}")
        else:
            test_logger.info("❌ Lost objects JSON file not found")
            
    except Exception as e:
        test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
