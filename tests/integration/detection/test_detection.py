#!/usr/bin/env python3

import sys
import os
from evileye.core.logging_config import setup_evileye_logging
from evileye.core.logger import get_module_logger

# Инициализация логирования для тестов
logger = setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
test_logger = get_module_logger("test")

def test_detection():
    """Test object detection with YOLO"""
    
    test_logger.info("=== Test Object Detection ===")
    
    try:
        from ultralytics import YOLO
        import cv2
        import numpy as np
        
        # Load model
        model_path = "models/yolov8n.pt"
        test_logger.info(f"Loading model: {model_path}")
        model = YOLO(model_path)
        
        # Test with a simple image or video frame
        video_path = "videos/6p-c0.avi"
        test_logger.info(f"Testing with video: {video_path}")
        
        # Open video
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            test_logger.error(f"❌ Error: Could not open video {video_path}")
            return
        
        # Read first frame
        ret, frame = cap.read()
        if not ret:
            test_logger.info("❌ Error: Could not read frame from video")
            cap.release()
            return
        
        test_logger.info(f"✅ Frame read successfully: {frame.shape}")
        
        # Run detection
        test_logger.info("Running detection...")
        results = model(frame, conf=0.1, verbose=False)
        
        # Check results
        for i, result in enumerate(results):
            boxes = result.boxes
            if boxes is not None:
                test_logger.info(f"✅ Detection successful! Found {len(boxes)} objects")
                
                # Print detected objects
                for j, box in enumerate(boxes):
                    cls = int(box.cls[0])
                    conf = float(box.conf[0])
                    coords = box.xyxy[0].cpu().numpy()
                    test_logger.info(f"  Object {j+1}: Class {cls}, Confidence {conf:.3f}, Coords {coords}")
            else:
                test_logger.info("❌ No objects detected")
        
        cap.release()
        
        # Test with planes video
        test_logger.info("\n--- Testing with planes video ---")
        planes_video = "videos/planes_sample.mp4"
        cap = cv2.VideoCapture(planes_video)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                test_logger.info(f"✅ Planes frame read: {frame.shape}")
                results = model(frame, conf=0.1, verbose=False)
                
                for i, result in enumerate(results):
                    boxes = result.boxes
                    if boxes is not None:
                        test_logger.info(f"✅ Planes detection: Found {len(boxes)} objects")
                        for j, box in enumerate(boxes):
                            cls = int(box.cls[0])
                            conf = float(box.conf[0])
                            coords = box.xyxy[0].cpu().numpy()
                            test_logger.info(f"  Object {j+1}: Class {cls}, Confidence {conf:.3f}, Coords {coords}")
                    else:
                        test_logger.info("❌ No objects detected in planes video")
            cap.release()
        
    except Exception as e:
        test_logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
