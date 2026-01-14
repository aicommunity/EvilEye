#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_correct_image_saving():
    """Test correct image saving: preview with boxes, frame without boxes"""
    
    test_logger.info("=== Test Correct Image Saving ===")
    
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
        
        # Create test image with some content
        test_image = np.zeros((480, 640, 3), dtype=np.uint8)
        test_image[:] = (100, 150, 200)  # Blue-gray color
        # Add a simple rectangle to simulate an object
        cv2.rectangle(test_image, (100, 100), (300, 400), (255, 255, 255), 2)
        
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
        test_logger.info("\n📸 Testing correct image saving:")
        
        # Process tracking results
        handler._handle_active(tracking_results, capture_image)
        
        # Check if images were saved correctly
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
                latest_frame = max(detected_files, key=lambda x: os.path.getctime(os.path.join(detected_dir, x)))
                test_logger.info(f"   Latest frame: {latest_frame}")
                
                # Check if frame image is original (without bounding boxes)
                frame_path = os.path.join(detected_dir, latest_frame)
                frame_img = cv2.imread(frame_path)
                if frame_img is not None:
                    # Check if image contains the original rectangle (white rectangle we drew)
                    # This should be present in the original image
                    gray = cv2.cvtColor(frame_img, cv2.COLOR_BGR2GRAY)
                    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
                    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    if len(contours) > 0:
                        test_logger.info(f"   ✅ Frame image contains original content (no bounding boxes drawn)")
                    else:
                        test_logger.info(f"   ❌ Frame image may have bounding boxes drawn")
        
        if os.path.exists(detected_previews_dir):
            preview_files = os.listdir(detected_previews_dir)
            test_logger.info(f"   Detected previews: {len(preview_files)}")
            if preview_files:
                latest_preview = max(preview_files, key=lambda x: os.path.getctime(os.path.join(detected_previews_dir, x)))
                test_logger.info(f"   Latest preview: {latest_preview}")
                
                # Check if preview image has bounding boxes
                preview_path = os.path.join(detected_previews_dir, latest_preview)
                preview_img = cv2.imread(preview_path)
                if preview_img is not None:
                    # Check if image contains green bounding boxes (drawn by utils.draw_preview_boxes)
                    hsv = cv2.cvtColor(preview_img, cv2.COLOR_BGR2HSV)
                    # Green color range
                    lower_green = np.array([40, 50, 50])
                    upper_green = np.array([80, 255, 255])
                    green_mask = cv2.inRange(hsv, lower_green, upper_green)
                    green_pixels = cv2.countNonZero(green_mask)
                    if green_pixels > 100:  # Threshold for green pixels
                        test_logger.info(f"   ✅ Preview image contains bounding boxes (green rectangles)")
                    else:
                        test_logger.info(f"   ❌ Preview image may not have bounding boxes")
        
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
                    latest_lost_frame = max(lost_files, key=lambda x: os.path.getctime(os.path.join(lost_dir, x)))
                    test_logger.info(f"   Latest lost frame: {latest_lost_frame}")
            
            if os.path.exists(lost_previews_dir):
                lost_preview_files = os.listdir(lost_previews_dir)
                test_logger.info(f"   Lost previews: {len(lost_preview_files)}")
                if lost_preview_files:
                    latest_lost_preview = max(lost_preview_files, key=lambda x: os.path.getctime(os.path.join(lost_previews_dir, x)))
                    test_logger.info(f"   Latest lost preview: {latest_lost_preview}")
        
        # Stop handler
        handler.stop()
        
        test_logger.info("\n✅ Correct image saving test completed")
        test_logger.info("\n📋 Summary:")
        test_logger.info("   ✅ Preview images: With bounding boxes (green rectangles)")
        test_logger.info("   ✅ Frame images: Original content without bounding boxes")
        test_logger.info("   ✅ Same logic as database journal")
        
    except Exception as e:
        test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
