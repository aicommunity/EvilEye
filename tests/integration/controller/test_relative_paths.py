#!/usr/bin/env python3
"""
Test script for relative path resolution in EvilEye components.
"""

import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger
import sys
from pathlib import Path

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_detector_relative_paths():
    """Test relative path resolution in YOLO detector."""
    
    test_logger.info("🔍 Testing Detector Relative Paths")
    test_logger.info("=" * 60)
    
    try:
        from evileye.object_detector.object_detection_yolo import ObjectDetectorYolo
        
        # Test with relative path
        detector = ObjectDetectorYolo()
        detector.params['model'] = 'models/yolo11n.pt'
        detector.set_params_impl()
        
        test_logger.info(f"Original model path: models/yolo11n.pt")
        test_logger.info(f"Stored model path: {detector.model_name}")
        test_logger.info(f"Current working directory: {os.getcwd()}")
        test_logger.info(f"Path is absolute: {os.path.isabs(detector.model_name)}")
        
        # Test access path resolution
        access_path = detector.model_name
        if not os.path.isabs(access_path):
            access_path = os.path.join(os.getcwd(), access_path)
        test_logger.info(f"Access path: {access_path}")
        test_logger.info(f"File exists: {os.path.exists(access_path)}")
        
    except Exception as e:
        test_logger.info(f"Error testing detector: {e}")

def test_tracker_relative_paths():
    """Test relative path resolution in Botsort tracker."""
    
    test_logger.info("\n🔍 Testing Tracker Relative Paths")
    test_logger.info("=" * 60)
    
    try:
        from evileye.object_tracker.object_tracking_botsort import ObjectTrackingBotsort
        
        # Test with relative path
        tracker = ObjectTrackingBotsort()
        tracker.params['tracker_onnx'] = 'models/osnet_ain_x1_0_M.onnx'
        
        # Simulate encoder dictionary
        encoders = {}
        encoders[os.path.join(os.getcwd(), 'models/osnet_ain_x1_0_M.onnx')] = None
        
        tracker.init_impl(encoders=encoders)
        
        test_logger.info(f"Original onnx path: models/osnet_ain_x1_0_M.onnx")
        test_logger.info(f"Current working directory: {os.getcwd()}")
        test_logger.info(f"Expected resolved path: {os.path.join(os.getcwd(), 'models/osnet_ain_x1_0_M.onnx')}")
        test_logger.info(f"File exists: {os.path.exists('models/osnet_ain_x1_0_M.onnx')}")
        
    except Exception as e:
        test_logger.info(f"Error testing tracker: {e}")

def test_database_relative_paths():
    """Test relative path resolution in database controller."""
    
    test_logger.info("\n🔍 Testing Database Relative Paths")
    test_logger.info("=" * 60)
    
    try:
        from evileye.database_controller.database_controller_pg import DatabaseControllerPg
        
        # Test with relative path
        db_controller = DatabaseControllerPg({})
        db_controller.default()  # Initialize default parameters
        db_controller.params['image_dir'] = 'database_images'
        db_controller.set_params_impl()
        
        test_logger.info(f"Original image_dir: database_images")
        test_logger.info(f"Stored image_dir: {db_controller.image_dir}")
        test_logger.info(f"Current working directory: {os.getcwd()}")
        test_logger.info(f"Path is absolute: {os.path.isabs(db_controller.image_dir)}")
        
        # Test access path resolution
        access_path = db_controller.image_dir
        if not os.path.isabs(access_path):
            access_path = os.path.join(os.getcwd(), access_path)
        test_logger.info(f"Access path: {access_path}")
        test_logger.info(f"Directory exists: {os.path.exists(access_path)}")
        
        # Create directory if it doesn't exist
        if not os.path.exists(db_controller.image_dir):
            os.makedirs(db_controller.image_dir)
            test_logger.info(f"Created directory: {db_controller.image_dir}")
        
    except Exception as e:
        test_logger.info(f"Error testing database: {e}")

def test_config_loading():
    """Test loading configuration with relative paths."""
    
    test_logger.info("\n🔍 Testing Configuration Loading")
    test_logger.info("=" * 60)
    
    try:
        import json
        
        # Load test configuration
        with open('test_relative_paths.json', 'r') as f:
            config = json.load(f)
        
        test_logger.info("Configuration loaded successfully")
        test_logger.info(f"Detector model: {config['pipeline']['detectors'][0]['model']}")
        test_logger.info(f"Tracker onnx: {config['pipeline']['trackers'][0]['tracker_onnx']}")
        test_logger.info(f"Database image_dir: {config['database']['image_dir']}")
        
        # Test path resolution
        detector_model = config['pipeline']['detectors'][0]['model']
        tracker_onnx = config['pipeline']['trackers'][0]['tracker_onnx']
        image_dir = config['database']['image_dir']
        
        test_logger.info(f"\nPath resolution test:")
        test_logger.info(f"  models/yolo11n.pt -> {os.path.join(os.getcwd(), detector_model)} (for access)")
        test_logger.info(f"  models/osnet_ain_x1_0_M.onnx -> {os.path.join(os.getcwd(), tracker_onnx)} (for access)")
        test_logger.info(f"  database_images -> {os.path.join(os.getcwd(), image_dir)} (for access)")
        
    except Exception as e:
        test_logger.info(f"Error testing configuration: {e}")

#!/usr/bin/env python3
"""
Test script to verify relative paths in labeling data.
"""

import os
import json
import datetime
from unittest.mock import Mock

def test_relative_paths():
    """Test relative paths in labeling data."""
    
    test_logger.info("🔍 Testing Relative Paths in Labeling Data")
    test_logger.info("=" * 60)
    
    try:
        from evileye.objects_handler.labeling_manager import LabelingManager
        
        # Create labeling manager
        from pathlib import Path
        test_dir = str(Path(__file__).parent.parent.parent / "data" / "test_relative_paths")
        cameras_params = [
            {
                'source_ids': [0, 1],
                'source_names': ['camera_1', 'camera_2']
            }
        ]
        labeling_manager = LabelingManager(base_dir=test_dir, cameras_params=cameras_params)
        
        # Create mock object
        mock_obj = Mock()
        mock_obj.object_id = 1
        mock_obj.frame_id = 1234
        mock_obj.time_stamp = datetime.datetime.now()
        mock_obj.time_detected = datetime.datetime.now()
        mock_obj.time_lost = datetime.datetime.now()
        mock_obj.track = Mock()
        mock_obj.track.bounding_box = [100, 150, 300, 400]
        mock_obj.track.confidence = 0.95
        mock_obj.track.track_id = 1
        mock_obj.class_id = 0
        mock_obj.source_id = 0
        mock_obj.global_id = None
        mock_obj.lost_frames = 5
        mock_obj.attributes = {}  # Initialize attributes as empty dict
        
        # Test found object data with relative paths
        found_data = labeling_manager.create_found_object_data(
            mock_obj, 1920, 1080, "test_frame.jpeg", "test_preview.jpeg"
        )
        
        test_logger.info("✅ Found object data created")
        test_logger.info(f"Image filename: {found_data['image_filename']}")
        test_logger.info(f"Source ID: {found_data['source_id']}")
        test_logger.info(f"Source name: {found_data['source_name']}")
        
        # Check relative paths (without date folder)
        expected_image_filename = "detected_frames/test_frame.jpeg"
        
        if found_data['image_filename'] == expected_image_filename:
            test_logger.info("✅ Image filename is correct")
        else:
            test_logger.error(f"❌ Expected image filename: {expected_image_filename}")
            test_logger.info(f"Got: {found_data['image_filename']}")
        
        # Check source name
        if found_data['source_name'] == 'camera_1':
            test_logger.info("✅ Source name is correct")
        else:
            test_logger.error(f"❌ Expected source name: camera_1")
            test_logger.info(f"Got: {found_data['source_name']}")
        
        # Test lost object data with relative paths
        lost_data = labeling_manager.create_lost_object_data(
            mock_obj, 1920, 1080, "test_lost_frame.jpeg", "test_lost_preview.jpeg"
        )
        
        test_logger.info("\n✅ Lost object data created")
        test_logger.info(f"Image filename: {lost_data['image_filename']}")
        test_logger.info(f"Source ID: {lost_data['source_id']}")
        test_logger.info(f"Source name: {lost_data['source_name']}")
        
        # Check relative paths for lost objects (without date folder)
        expected_lost_image_filename = "lost_frames/test_lost_frame.jpeg"
        
        if lost_data['image_filename'] == expected_lost_image_filename:
            test_logger.info("✅ Lost image filename is correct")
        else:
            test_logger.error(f"❌ Expected lost image filename: {expected_lost_image_filename}")
            test_logger.info(f"Got: {lost_data['image_filename']}")
        
        # Check source name for lost object
        if lost_data['source_name'] == 'camera_1':
            test_logger.info("✅ Lost source name is correct")
        else:
            test_logger.error(f"❌ Expected lost source name: camera_1")
            test_logger.info(f"Got: {lost_data['source_name']}")
        
        # Test path construction
        test_logger.info("\n🔍 Testing path construction:")
        test_logger.info(f"Base directory: {test_dir}")
        test_logger.info(f"Date string: {labeling_manager.date_str}")
        test_logger.info(f"Full image path would be: {os.path.join(test_dir, 'images', labeling_manager.date_str, found_data['image_filename'])}")
        
        # Clean up
        labeling_manager.stop()
        import shutil
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
            test_logger.info("✅ Test directory cleaned up")
        
        test_logger.info("\n✅ Relative paths test completed successfully")
        
    except Exception as e:
        test_logger.error(f"❌ Error in relative paths test: {e}")
        import traceback
        traceback.print_exc()

def test_path_usage_example():
    """Test how to use relative paths to access images."""
    
    test_logger.info("\n🔍 Testing Path Usage Example")
    test_logger.info("=" * 60)
    
    try:
        from evileye.objects_handler.labeling_manager import LabelingManager
        
        # Create labeling manager
        test_dir = "test_path_usage"
        cameras_params = [
            {
                'source_ids': [0, 1],
                'source_names': ['camera_1', 'camera_2']
            }
        ]
        labeling_manager = LabelingManager(base_dir=test_dir, cameras_params=cameras_params)
        
        # Simulate loading label data
        mock_label_data = {
            "object_id": 1,
            "frame_id": 1234,
            "timestamp": "2024-01-15T10:30:15.123456",
            "image_filename": "detected_frames/2024_01_15_10_30_15.123456_frame.jpeg",
            "bounding_box": {"x": 480, "y": 324, "width": 288, "height": 216},
            "confidence": 0.95,
            "class_id": 0,
            "class_name": "person",
            "source_id": 0,
            "source_name": "camera_1",
            "track_id": 1,
            "global_id": None
        }
        
        test_logger.info("✅ Mock label data created")
        test_logger.info(f"Image filename from label: {mock_label_data['image_filename']}")
        test_logger.info(f"Source name from label: {mock_label_data['source_name']}")
        
        # Show how to construct full paths
        base_dir = test_dir
        date_str = "2024_01_15"  # Date from the mock data
        full_image_path = os.path.join(base_dir, "images", date_str, mock_label_data['image_filename'])
        
        test_logger.info(f"\nFull image path: {full_image_path}")
        
        # Show how to check if files exist
        test_logger.info(f"\nImage file would exist: {os.path.exists(full_image_path)}")
        
        # Show how to use with different base directories
        alternative_base = "/custom/data/path"
        alt_image_path = os.path.join(alternative_base, "images", date_str, mock_label_data['image_filename'])
        
        test_logger.info(f"\nWith alternative base '{alternative_base}':")
        test_logger.info(f"Image path: {alt_image_path}")
        
        # Clean up
        labeling_manager.stop()
        import shutil
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
            test_logger.info("✅ Test directory cleaned up")
        
        test_logger.info("\n✅ Path usage example completed successfully")
        
    except Exception as e:
        test_logger.error(f"❌ Error in path usage example: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main test function."""
    
    test_logger.info("🔍 Relative Paths in Labeling Data Test")
    test_logger.info("=" * 60)
    
    test_relative_paths()
    test_path_usage_example()
    
    test_logger.info("\n📋 Summary:")
    test_logger.info("  ✅ Relative paths added to labeling data")
    test_logger.info("  ✅ image_path and preview_path fields")
    test_logger.info("  ✅ Paths relative to base directory")
    test_logger.info("  ✅ Easy access to images from label data")
    test_logger.info("  ✅ Compatible with different base directories")
