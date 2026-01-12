#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger
import time
import json
import datetime

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_frequent_updates():
    """Test frequent updates of JSON files"""
    
    test_logger.info("=== Test Frequent Updates ===")
    
    try:
        from evileye.objects_handler.labeling_manager import LabelingManager
        
        # Create test directory
        base_dir = 'EvilEyeData'
        today = datetime.date.today().strftime('%Y_%m_%d')
        test_dir = os.path.join(base_dir, 'images', today)
        os.makedirs(test_dir, exist_ok=True)
        
        # Create labeling manager
        labeling_manager = LabelingManager(base_dir=base_dir, cameras_params=[])
        
        test_logger.info(f"✅ Created labeling manager")
        test_logger.info(f"   Buffer size: {labeling_manager.buffer_size}")
        test_logger.info(f"   Save interval: {labeling_manager.save_interval} seconds")
        
        # Test object data
        test_object = {
            "object_id": 999,
            "frame_id": 999,
            "timestamp": datetime.datetime.now().isoformat(),
            "image_filename": "detected_frames/test_frame.jpeg",
            "bounding_box": {
                "x": 100,
                "y": 100,
                "width": 200,
                "height": 200
            },
            "confidence": 0.95,
            "class_id": 0,
            "class_name": "person",
            "source_id": 0,
            "source_name": "Cam1",
            "track_id": 999,
            "global_id": None
        }
        
        test_logger.info("\n🧪 Testing Frequent Updates:")
        test_logger.info("   - Adding objects to buffer")
        test_logger.info("   - Checking if files update more frequently")
        
        # Add objects and monitor file changes
        for i in range(10):
            # Update object ID
            test_object["object_id"] = 1000 + i
            test_object["timestamp"] = datetime.datetime.now().isoformat()
            
            # Add to buffer
            labeling_manager.add_object_found(test_object)
            
            test_logger.info(f"   ✅ Added object {1000 + i}")
            
            # Check if file was updated
            found_file = labeling_manager.found_labels_file
            if os.path.exists(found_file):
                stat = os.stat(found_file)
                test_logger.info(f"      File last modified: {datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%H:%M:%S')}")
            
            # Wait a bit
            time.sleep(2)
        
        # Force save
        test_logger.info("\n   🔄 Forcing buffer flush...")
        labeling_manager.flush_buffers()
        
        # Check final state
        stats = labeling_manager.get_statistics()
        test_logger.info(f"\n📊 Final Statistics:")
        test_logger.info(f"   Found objects: {stats['found_objects']}")
        test_logger.info(f"   Lost objects: {stats['lost_objects']}")
        test_logger.info(f"   Total objects: {stats['total_objects']}")
        
        # Stop labeling manager
        labeling_manager.stop()
        
        test_logger.info("\n✅ Test completed successfully!")
        
    except Exception as e:
        test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
