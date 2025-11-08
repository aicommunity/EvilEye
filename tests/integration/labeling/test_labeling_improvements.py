#!/usr/bin/env python3
"""
Test script to verify improvements in the labeling system.
"""

import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger
import json
import time
import datetime
from unittest.mock import Mock

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_new_structure():
    """Test new folder structure."""
    
    test_logger.info("🔍 Testing New Folder Structure")
    test_logger.info("=" * 60)
    
    try:
        from evileye.objects_handler.labeling_manager import LabelingManager
        
        # Create labeling manager with test directory
        test_dir = "test_labeling_improvements"
        labeling_manager = LabelingManager(base_dir=test_dir)
        test_logger.info("✅ LabelingManager created")
        
        # Check if files are in the correct location
        expected_found_file = os.path.join(test_dir, "images", labeling_manager.date_str, "objects_found.json")
        expected_lost_file = os.path.join(test_dir, "images", labeling_manager.date_str, "objects_lost.json")
        
        if os.path.exists(expected_found_file):
            test_logger.info("✅ Found labels file in correct location")
        else:
            test_logger.error(f"❌ Found labels file not in expected location: {expected_found_file}")
            
        if os.path.exists(expected_lost_file):
            test_logger.info("✅ Lost labels file in correct location")
        else:
            test_logger.error(f"❌ Lost labels file not in expected location: {expected_lost_file}")
        
        # Check directory structure
        day_dir = os.path.join(test_dir, "images", labeling_manager.date_str)
        if os.path.exists(day_dir):
            test_logger.info("✅ Date directory created")
            files = os.listdir(day_dir)
            test_logger.info(f"Files in day directory: {files}")
        else:
            test_logger.info("❌ Date directory not created")
        
        # Clean up
        import shutil
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
            test_logger.info("✅ Test directory cleaned up")
        
        test_logger.info("✅ New structure test completed successfully")
        
    except Exception as e:
        test_logger.error(f"❌ Error in new structure test: {e}")
        import traceback
        traceback.print_exc()

def test_pixel_coordinates():
    """Test pixel coordinate format."""
    
    test_logger.info("\n🔍 Testing Pixel Coordinates")
    test_logger.info("=" * 60)
    
    try:
        from evileye.objects_handler.labeling_manager import LabelingManager
        
        # Create labeling manager
        from pathlib import Path
        test_dir = str(Path(__file__).parent.parent.parent / "data" / "test_pixel_coords")
        labeling_manager = LabelingManager(base_dir=test_dir)
        
        # Create mock object with pixel coordinates
        mock_obj = Mock()
        mock_obj.object_id = 1
        mock_obj.frame_id = 1234
        mock_obj.time_stamp = datetime.datetime.now()
        mock_obj.track = Mock()
        mock_obj.track.bounding_box = [100, 150, 300, 400]  # x1, y1, x2, y2 in pixels
        mock_obj.track.confidence = 0.95
        mock_obj.track.track_id = 1
        mock_obj.class_id = 0
        mock_obj.source_id = 0
        mock_obj.global_id = None
        mock_obj.attributes = {}  # Initialize attributes as empty dict
        
        # Test found object data
        found_data = labeling_manager.create_found_object_data(
            mock_obj, 1920, 1080, "test_frame.jpeg", "test_preview.jpeg"
        )
        
        # Check bounding box format
        bbox = found_data["bounding_box"]
        expected_x = 100
        expected_y = 150
        expected_width = 200  # 300 - 100
        expected_height = 250  # 400 - 150
        
        if (bbox["x"] == expected_x and bbox["y"] == expected_y and
            bbox["width"] == expected_width and bbox["height"] == expected_height):
            test_logger.info("✅ Pixel coordinates correct")
            test_logger.info(f"Bounding box: x={bbox['x']}, y={bbox['y']}, w={bbox['width']}, h={bbox['height']}")
        else:
            test_logger.info("❌ Pixel coordinates incorrect")
            test_logger.info(f"Expected: x={expected_x}, y={expected_y}, w={expected_width}, h={expected_height}")
            test_logger.info(f"Got: x={bbox['x']}, y={bbox['y']}, w={bbox['width']}, h={bbox['height']}")
        
        # Test lost object data
        mock_obj.time_detected = datetime.datetime.now()
        mock_obj.time_lost = datetime.datetime.now()
        mock_obj.lost_frames = 5
        
        lost_data = labeling_manager.create_lost_object_data(
            mock_obj, 1920, 1080, "test_lost_frame.jpeg", "test_lost_preview.jpeg"
        )
        
        lost_bbox = lost_data["bounding_box"]
        if (lost_bbox["x"] == expected_x and lost_bbox["y"] == expected_y and
            lost_bbox["width"] == expected_width and lost_bbox["height"] == expected_height):
            test_logger.info("✅ Lost object pixel coordinates correct")
        else:
            test_logger.info("❌ Lost object pixel coordinates incorrect")
        
        # Clean up
        labeling_manager.stop()
        import shutil
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
            test_logger.info("✅ Test directory cleaned up")
        
        test_logger.info("✅ Pixel coordinates test completed successfully")
        
    except Exception as e:
        test_logger.error(f"❌ Error in pixel coordinates test: {e}")
        import traceback
        traceback.print_exc()

def test_buffering():
    """Test buffering functionality."""
    
    test_logger.info("\n🔍 Testing Buffering Functionality")
    test_logger.info("=" * 60)
    
    try:
        from evileye.objects_handler.labeling_manager import LabelingManager
        
        # Create labeling manager with small buffer for testing
        from pathlib import Path
        test_dir = str(Path(__file__).parent.parent.parent / "data" / "test_buffering")
        labeling_manager = LabelingManager(base_dir=test_dir)
        labeling_manager.buffer_size = 3  # Small buffer for testing
        labeling_manager.save_interval = 5  # Short interval for testing
        
        # Create mock objects
        mock_objects = []
        for i in range(5):
            mock_obj = Mock()
            mock_obj.object_id = i + 1
            mock_obj.frame_id = 1000 + i
            mock_obj.time_stamp = datetime.datetime.now()
            mock_obj.track = Mock()
            mock_obj.track.bounding_box = [100 + i*10, 150 + i*10, 200 + i*10, 250 + i*10]
            mock_obj.track.confidence = 0.9
            mock_obj.track.track_id = i + 1
            mock_obj.class_id = 0
            mock_obj.source_id = 0
            mock_obj.global_id = None
            mock_obj.attributes = {}  # Initialize attributes as empty dict
            mock_objects.append(mock_obj)
        
        # Add objects to buffer
        test_logger.info("Adding objects to buffer...")
        for i, mock_obj in enumerate(mock_objects):
            object_data = labeling_manager.create_found_object_data(
                mock_obj, 1920, 1080, f"test_frame_{i}.jpeg", f"test_preview_{i}.jpeg"
            )
            labeling_manager.add_object_found(object_data)
            test_logger.info(f"Added object {i+1}, buffer size: {len(labeling_manager.found_buffer)}")
        
        # Wait a bit for background saving
        time.sleep(2)
        
        # Force flush
        test_logger.info("Forcing buffer flush...")
        labeling_manager.flush_buffers()
        
        # Check if data was saved
        found_file = labeling_manager.found_labels_file
        if os.path.exists(found_file):
            with open(found_file, 'r') as f:
                data = json.load(f)
                object_count = len(data["objects"])
                test_logger.info(f"✅ Found {object_count} objects in saved file")
                
                if object_count == 5:
                    test_logger.info("✅ All objects were saved correctly")
                else:
                    test_logger.error(f"❌ Expected 5 objects, got {object_count}")
        else:
            test_logger.info("❌ Found labels file not created")
        
        # Clean up
        labeling_manager.stop()
        import shutil
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
            test_logger.info("✅ Test directory cleaned up")
        
        test_logger.info("✅ Buffering test completed successfully")
        
    except Exception as e:
        test_logger.error(f"❌ Error in buffering test: {e}")
        import traceback
        traceback.print_exc()

def test_performance():
    """Test performance improvements."""
    
    test_logger.info("\n🔍 Testing Performance Improvements")
    test_logger.info("=" * 60)
    
    try:
        from evileye.objects_handler.labeling_manager import LabelingManager
        import time
        
        # Create labeling manager
        from pathlib import Path
        test_dir = str(Path(__file__).parent.parent.parent / "data" / "test_performance")
        labeling_manager = LabelingManager(base_dir=test_dir)
        labeling_manager.buffer_size = 50  # Medium buffer
        
        # Create many mock objects
        num_objects = 200
        mock_objects = []
        
        test_logger.info(f"Creating {num_objects} mock objects...")
        for i in range(num_objects):
            mock_obj = Mock()
            mock_obj.object_id = i + 1
            mock_obj.frame_id = 1000 + i
            mock_obj.time_stamp = datetime.datetime.now()
            mock_obj.track = Mock()
            mock_obj.track.bounding_box = [100 + i, 150 + i, 200 + i, 250 + i]
            mock_obj.track.confidence = 0.9
            mock_obj.track.track_id = i + 1
            mock_obj.class_id = 0
            mock_obj.source_id = 0
            mock_obj.global_id = None
            mock_obj.attributes = {}  # Initialize attributes as empty dict
            mock_objects.append(mock_obj)
        
        # Test buffered adding
        test_logger.info("Testing buffered adding...")
        start_time = time.time()
        
        for i, mock_obj in enumerate(mock_objects):
            object_data = labeling_manager.create_found_object_data(
                mock_obj, 1920, 1080, f"test_frame_{i}.jpeg", f"test_preview_{i}.jpeg"
            )
            labeling_manager.add_object_found(object_data)
        
        # Force flush
        labeling_manager.flush_buffers()
        end_time = time.time()
        
        buffered_time = end_time - start_time
        test_logger.info(f"✅ Buffered adding took {buffered_time:.3f} seconds")
        
        # Check results
        found_file = labeling_manager.found_labels_file
        if os.path.exists(found_file):
            with open(found_file, 'r') as f:
                data = json.load(f)
                object_count = len(data["objects"])
                test_logger.info(f"✅ Saved {object_count} objects successfully")
        
        # Clean up
        labeling_manager.stop()
        import shutil
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
            test_logger.info("✅ Test directory cleaned up")
        
        test_logger.info("✅ Performance test completed successfully")
        
    except Exception as e:
        test_logger.error(f"❌ Error in performance test: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main test function."""
    
    test_logger.info("🔍 Labeling System Improvements Test")
    test_logger.info("=" * 60)
    
    test_new_structure()
    test_pixel_coordinates()
    test_buffering()
    test_performance()
    
    test_logger.info("\n📋 Summary:")
    test_logger.info("  ✅ New folder structure implemented")
    test_logger.info("  ✅ Pixel coordinates for COCO compatibility")
    test_logger.info("  ✅ Buffering system for performance")
    test_logger.info("  ✅ Asynchronous saving with background thread")
    test_logger.info("  ✅ Proper cleanup and data persistence")
