#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_image_saving():
    """Test image saving without database"""
    
    test_logger.info("=== Test Image Saving Without Database ===")
    
    try:
        from evileye.objects_handler.objects_handler import ObjectsHandler
        from evileye.object_tracker.tracking_results import TrackingResult, TrackingResultList
        from evileye.capture.video_capture_base import CaptureImage
        import cv2
        import numpy as np
        import datetime
        
        # Create mock objects
        class MockDBController:
            def get_params(self):
                return {
                    'image_dir': 'EvilEyeData',
                    'preview_width': 300,
                    'preview_height': 150
                }
            
            def get_cameras_params(self):
                return [
                    {
                        'source_ids': [0],
                        'source_names': ['Cam1'],
                        'camera': 'test_camera'
                    }
                ]
            
            def get_project_id(self):
                return 1
            
            def get_job_id(self):
                return 1
        
        class MockDBAdapter:
            def insert(self, obj):
                test_logger.info(f"Mock DB: Insert object {obj.object_id}")
            
            def update(self, obj):
                test_logger.info(f"Mock DB: Update object {obj.object_id}")
        
        # Create test image
        test_image = np.zeros((480, 640, 3), dtype=np.uint8)
        test_image[:] = (100, 150, 200)  # Blue-gray color
        
        # Create CaptureImage
        capture_image = CaptureImage()
        capture_image.image = test_image
        capture_image.width = 640
        capture_image.height = 480
        capture_image.source_id = 0
        capture_image.current_video_position = 0
        
        # Create tracking result
        track = TrackingResult()
        track.track_id = 1
        track.class_id = 0  # person
        track.confidence = 0.85
        track.bounding_box = [100, 100, 200, 300]  # x, y, width, height
        track.tracking_data = {'global_id': 1}
        
        tracking_results = TrackingResultList()
        tracking_results.source_id = 0
        tracking_results.frame_id = 1
        tracking_results.time_stamp = datetime.datetime.now()
        tracking_results.tracks = [track]
        
        # Create ObjectsHandler without database
        db_controller = MockDBController()
        db_adapter = MockDBAdapter()
        
        handler = ObjectsHandler(db_controller, db_adapter)
        handler.params = {
            'lost_store_time_secs': 60,
            'history_len': 1,
            'lost_thresh': 5,
            'max_active_objects': 100,
            'max_lost_objects': 100
        }
        handler.set_params_impl()
        
        test_logger.info("✅ ObjectsHandler created")
        
        # Test image saving
        test_logger.info("\n📸 Testing image saving:")
        
        # Process tracking results
        handler._handle_active(tracking_results, capture_image)
        
        # Check if images were saved
        test_logger.info("\n📁 Checking saved images:")
        
        # Look for saved images
        base_dir = 'EvilEyeData'
        today = datetime.date.today().strftime('%Y_%m_%d')
        
        detected_dir = os.path.join(base_dir, 'images', today, 'detected_frames')
        detected_previews_dir = os.path.join(base_dir, 'images', today, 'detected_previews')
        
        if os.path.exists(detected_dir):
            detected_files = os.listdir(detected_dir)
            test_logger.info(f"   Detected frames: {len(detected_files)}")
            if detected_files:
                test_logger.info(f"   Sample frame: {detected_files[0]}")
        
        if os.path.exists(detected_previews_dir):
            preview_files = os.listdir(detected_previews_dir)
            test_logger.info(f"   Detected previews: {len(preview_files)}")
            if preview_files:
                test_logger.info(f"   Sample preview: {preview_files[0]}")
        
        # Test lost object
        test_logger.info("\n🔍 Testing lost object:")
        
        # Simulate object becoming lost
        if handler.active_objs.objects:
            obj = handler.active_objs.objects[0]
            obj.lost_frames = 5  # Trigger lost threshold
            obj.last_update = False
            
            # Process again to trigger lost event
            handler._handle_active(tracking_results, capture_image)
            
            # Check lost images
            lost_dir = os.path.join(base_dir, 'images', today, 'lost_frames')
            lost_previews_dir = os.path.join(base_dir, 'images', today, 'lost_previews')
            
            if os.path.exists(lost_dir):
                lost_files = os.listdir(lost_dir)
                test_logger.info(f"   Lost frames: {len(lost_files)}")
                if lost_files:
                    test_logger.info(f"   Sample lost frame: {lost_files[0]}")
            
            if os.path.exists(lost_previews_dir):
                lost_preview_files = os.listdir(lost_previews_dir)
                test_logger.info(f"   Lost previews: {len(lost_preview_files)}")
                if lost_preview_files:
                    test_logger.info(f"   Sample lost preview: {lost_preview_files[0]}")
        
        # Stop handler
        handler.stop()
        
        test_logger.info("\n✅ Image saving test completed")
        
    except Exception as e:
        test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
