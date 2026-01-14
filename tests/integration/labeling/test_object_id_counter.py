#!/usr/bin/env python3
"""
Test script for object_id counter initialization from existing JSON files.
"""

import os
import json
import tempfile
import shutil
from datetime import datetime
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test_object_id_counter")

def create_test_json_files():
    """Create test JSON files with existing object_ids."""
    
    # Create temporary directory
    temp_dir = tempfile.mkdtemp()
    test_date = "2025_09_01"
    test_dir = os.path.join(temp_dir, "EvilEyeData", "images", test_date)
    os.makedirs(test_dir, exist_ok=True)
    
    # Create found objects file with existing IDs
    found_file = os.path.join(test_dir, "objects_found.json")
    found_data = {
        "metadata": {
            "version": "1.0",
            "created": datetime.now().isoformat(),
            "description": "Test found objects",
            "total_objects": 3
        },
        "objects": [
            {
                "object_id": 1,
                "timestamp": "2025-09-01T10:00:00",
                "class_name": "person",
                "confidence": 0.95
            },
            {
                "object_id": 5,
                "timestamp": "2025-09-01T10:01:00",
                "class_name": "car",
                "confidence": 0.87
            },
            {
                "object_id": 12,
                "timestamp": "2025-09-01T10:02:00",
                "class_name": "bicycle",
                "confidence": 0.78
            }
        ]
    }
    
    with open(found_file, 'w', encoding='utf-8') as f:
        json.dump(found_data, f, indent=2)
    
    # Create lost objects file with existing IDs
    lost_file = os.path.join(test_dir, "objects_lost.json")
    lost_data = {
        "metadata": {
            "version": "1.0",
            "created": datetime.now().isoformat(),
            "description": "Test lost objects",
            "total_objects": 2
        },
        "objects": [
            {
                "object_id": 3,
                "detected_timestamp": "2025-09-01T09:58:00",
                "lost_timestamp": "2025-09-01T10:03:00",
                "class_name": "person",
                "confidence": 0.92
            },
            {
                "object_id": 8,
                "detected_timestamp": "2025-09-01T09:59:00",
                "lost_timestamp": "2025-09-01T10:04:00",
                "class_name": "car",
                "confidence": 0.89
            }
        ]
    }
    
    with open(lost_file, 'w', encoding='utf-8') as f:
        json.dump(lost_data, f, indent=2)
    
    test_logger.info(f"✅ Созданы тестовые JSON файлы в: {test_dir}")
    test_logger.info(f"📁 Найденные объекты: {found_file}")
    test_logger.info(f"📁 Потерянные объекты: {lost_file}")
    
    return temp_dir, test_dir

def test_labeling_manager():
    """Test LabelingManager's _get_max_object_id method."""
    
    test_logger.info("\n🔍 Testing LabelingManager _get_max_object_id method")
    test_logger.info("=" * 60)
    
    try:
        from evileye.objects_handler.labeling_manager import LabelingManager
        
        # Create test files
        temp_dir, test_dir = create_test_json_files()
        
        # Create LabelingManager with test directory
        base_dir = os.path.join(temp_dir, "EvilEyeData")
        labeling_manager = LabelingManager(base_dir=base_dir)
        
        # Manually set the test date directory
        test_date = "2025_09_01"
        labeling_manager.current_date = datetime.strptime(test_date, "%Y_%m_%d").date()
        labeling_manager.date_str = test_date
        labeling_manager.current_day_dir = os.path.join(labeling_manager.images_dir, test_date)
        labeling_manager.found_labels_file = os.path.join(labeling_manager.current_day_dir, 'objects_found.json')
        labeling_manager.lost_labels_file = os.path.join(labeling_manager.current_day_dir, 'objects_lost.json')
        
        # Test _get_max_object_id method
        found_objects = labeling_manager._load_json(labeling_manager.found_labels_file, labeling_manager.found_file_lock).get("objects", [])
        lost_objects = labeling_manager._load_json(labeling_manager.lost_labels_file, labeling_manager.lost_file_lock).get("objects", [])
        
        max_id = labeling_manager._get_max_object_id(found_objects, lost_objects)
        
        test_logger.info(f"📊 Found objects: {len(found_objects)}")
        test_logger.info(f"📊 Lost objects: {len(lost_objects)}")
        test_logger.info(f"🔢 Maximum object_id: {max_id}")
        
        # Expected: max(1, 5, 12, 3, 8) = 12
        expected_max = 12
        if max_id == expected_max:
            test_logger.info(f"✅ Test passed: max_id = {max_id} (expected: {expected_max})")
        else:
            test_logger.info(f"❌ Test failed: max_id = {max_id} (expected: {expected_max})")
        
        # Test _preload_existing_data method
        test_logger.info(f"\n🔍 Testing _preload_existing_data method")
        test_logger.info("-" * 40)
        
        max_id_from_preload = labeling_manager._preload_existing_data()
        test_logger.info(f"🔢 Max ID from preload: {max_id_from_preload}")
        
        if max_id_from_preload == expected_max:
            test_logger.info(f"✅ Preload test passed: max_id = {max_id_from_preload} (expected: {expected_max})")
        else:
            test_logger.info(f"❌ Preload test failed: max_id = {max_id_from_preload} (expected: {expected_max})")
        
        # Cleanup
        shutil.rmtree(temp_dir)
        test_logger.info(f"\n🧹 Cleaned up test directory: {temp_dir}")
        
    except Exception as e:
        test_logger.info(f"❌ Error in LabelingManager test: {e}")
        import traceback
        traceback.print_exc()

def test_objects_handler():
    """Test ObjectsHandler's object_id counter initialization."""
    
    test_logger.info("\n🔍 Testing ObjectsHandler object_id counter initialization")
    test_logger.info("=" * 60)
    
    try:
        from evileye.objects_handler.objects_handler import ObjectsHandler
        
        # Create test files
        temp_dir, test_dir = create_test_json_files()
        
        # Create ObjectsHandler with test directory
        base_dir = os.path.join(temp_dir, "EvilEyeData")
        
        # Mock parameters - ObjectsHandler expects db_controller and db_adapter
        db_controller = None  # No database
        db_adapter = None
        
        # Create ObjectsHandler
        obj_handler = ObjectsHandler(db_controller, db_adapter)
        
        # Manually set the base directory for labeling manager
        test_date = "2025_09_01"
        obj_handler.labeling_manager.base_dir = base_dir
        obj_handler.labeling_manager.images_dir = os.path.join(base_dir, 'images')
        obj_handler.labeling_manager.current_date = datetime.strptime(test_date, "%Y_%m_%d").date()
        obj_handler.labeling_manager.date_str = test_date
        obj_handler.labeling_manager.current_day_dir = os.path.join(obj_handler.labeling_manager.images_dir, test_date)
        obj_handler.labeling_manager.found_labels_file = os.path.join(obj_handler.labeling_manager.current_day_dir, 'objects_found.json')
        obj_handler.labeling_manager.lost_labels_file = os.path.join(obj_handler.labeling_manager.current_day_dir, 'objects_lost.json')
        
        # Re-initialize the object_id counter with test data
        obj_handler._init_object_id_counter()
        
        test_logger.info(f"🔢 Initial object_id_counter: {obj_handler.object_id_counter}")
        
        # Expected: max(1, 5, 12, 3, 8) + 1 = 13
        expected_counter = 13
        if obj_handler.object_id_counter == expected_counter:
            test_logger.info(f"✅ Test passed: counter = {obj_handler.object_id_counter} (expected: {expected_counter})")
        else:
            test_logger.info(f"❌ Test failed: counter = {obj_handler.object_id_counter} (expected: {expected_counter})")
        
        # Test adding new objects
        test_logger.info(f"\n🔍 Testing object creation with new IDs")
        test_logger.info("-" * 40)
        
        # Simulate creating a new object
        old_counter = obj_handler.object_id_counter
        obj_handler.object_id_counter += 1
        new_counter = obj_handler.object_id_counter
        
        test_logger.info(f"🔢 Counter before increment: {old_counter}")
        test_logger.info(f"🔢 Counter after increment: {new_counter}")
        
        if new_counter == old_counter + 1:
            test_logger.info(f"✅ Counter increment test passed")
        else:
            test_logger.info(f"❌ Counter increment test failed")
        
        # Cleanup
        shutil.rmtree(temp_dir)
        test_logger.info(f"\n🧹 Cleaned up test directory: {temp_dir}")
        
    except Exception as e:
        test_logger.info(f"❌ Error in ObjectsHandler test: {e}")
        import traceback
        traceback.print_exc()
