#!/usr/bin/env python3
"""
Labeling Manager for saving object detection and tracking labels to JSON files.
"""

import json
import os
import datetime
import time
import threading
from typing import Dict, List, Any, Optional
from pathlib import Path
from queue import Queue
from threading import Thread, Lock


class LabelingManager:
    """
    Manages saving object detection and tracking labels to JSON files.
    
    Creates and maintains two JSON files:
    - objects_found.json: For objects detected for the first time
    - objects_lost.json: For objects that were lost (tracking ended)
    """
    
    def __init__(self, base_dir: str = 'EvilEyeData'):
        """
        Initialize the labeling manager.
        
        Args:
            base_dir: Base directory for saving labels and images
        """
        self.base_dir = base_dir
        self.images_dir = os.path.join(base_dir, 'images')
        
        # Create base directory if it doesn't exist
        os.makedirs(self.images_dir, exist_ok=True)
        
        # Current date for file naming
        self.current_date = datetime.date.today()
        self.date_str = self.current_date.strftime('%Y_%m_%d')
        
        # Create date-specific directory
        self.current_day_dir = os.path.join(self.images_dir, self.date_str)
        os.makedirs(self.current_day_dir, exist_ok=True)
        
        # File paths - now in the same directory as images
        self.found_labels_file = os.path.join(self.current_day_dir, 'objects_found.json')
        self.lost_labels_file = os.path.join(self.current_day_dir, 'objects_lost.json')
        
        # Initialize files if they don't exist
        self._init_label_files()
        
        # Buffering configuration
        self.buffer_size = 100  # Save when buffer reaches this size
        self.save_interval = 30  # Save every N seconds
        self.found_buffer = []
        self.lost_buffer = []
        self.last_save_time = time.time()
        self.running = True
        self.buffer_lock = Lock()
        
        # Start background save thread
        self.save_thread = Thread(target=self._save_worker, daemon=True)
        self.save_thread.start()
    
    def _init_label_files(self):
        """Initialize JSON label files if they don't exist."""
        
        # Initialize objects_found.json
        if not os.path.exists(self.found_labels_file):
            found_data = {
                "metadata": {
                    "version": "1.0",
                    "created": datetime.datetime.now().isoformat(),
                    "description": "Object detection labels - objects found for the first time",
                    "total_objects": 0
                },
                "objects": []
            }
            self._save_json(self.found_labels_file, found_data)
        
        # Initialize objects_lost.json
        if not os.path.exists(self.lost_labels_file):
            lost_data = {
                "metadata": {
                    "version": "1.0",
                    "created": datetime.datetime.now().isoformat(),
                    "description": "Object tracking labels - objects that were lost",
                    "total_objects": 0
                },
                "objects": []
            }
            self._save_json(self.lost_labels_file, lost_data)
    
    def _load_json(self, file_path: str) -> Dict[str, Any]:
        """Load JSON file safely."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def _save_json(self, file_path: str, data: Dict[str, Any]):
        """Save JSON file safely."""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving JSON file {file_path}: {e}")
    
    def _update_metadata(self, data: Dict[str, Any], total_objects: int):
        """Update metadata in label data."""
        data["metadata"]["last_updated"] = datetime.datetime.now().isoformat()
        data["metadata"]["total_objects"] = total_objects
    
    def add_object_found(self, object_data: Dict[str, Any]):
        """
        Add a newly detected object to the found labels buffer.
        
        Args:
            object_data: Dictionary containing object information
        """
        with self.buffer_lock:
            self.found_buffer.append(object_data)
            
            # Save if buffer is full
            if len(self.found_buffer) >= self.buffer_size:
                self._save_found_buffer()
    
    def _save_found_buffer(self):
        """Save found objects buffer to file."""
        if not self.found_buffer:
            return
            
        with self.buffer_lock:
            # Load current data
            data = self._load_json(self.found_labels_file)
            
            # Add all buffered objects
            data["objects"].extend(self.found_buffer)
            
            # Update metadata
            self._update_metadata(data, len(data["objects"]))
            
            # Save updated data
            self._save_json(self.found_labels_file, data)
            
            # Clear buffer
            self.found_buffer.clear()
    
    def add_object_lost(self, object_data: Dict[str, Any]):
        """
        Add a lost object to the lost labels buffer.
        
        Args:
            object_data: Dictionary containing object information
        """
        with self.buffer_lock:
            self.lost_buffer.append(object_data)
            
            # Save if buffer is full
            if len(self.lost_buffer) >= self.buffer_size:
                self._save_lost_buffer()
    
    def _save_lost_buffer(self):
        """Save lost objects buffer to file."""
        if not self.lost_buffer:
            return
            
        with self.buffer_lock:
            # Load current data
            data = self._load_json(self.lost_labels_file)
            
            # Add all buffered objects
            data["objects"].extend(self.lost_buffer)
            
            # Update metadata
            self._update_metadata(data, len(data["objects"]))
            
            # Save updated data
            self._save_json(self.lost_labels_file, data)
            
            # Clear buffer
            self.lost_buffer.clear()
    
    def create_found_object_data(self, obj, image_width: int, image_height: int, 
                                image_filename: str, preview_filename: str) -> Dict[str, Any]:
        """
        Create object data dictionary for found objects.
        
        Args:
            obj: ObjectResult object
            image_width: Width of the image
            image_height: Height of the image
            image_filename: Name of the saved image file
            preview_filename: Name of the saved preview file
            
        Returns:
            Dictionary with object data in labeling format
        """
        # Use absolute pixel coordinates for COCO compatibility
        bbox = obj.track.bounding_box
        pixel_bbox = {
            "x": int(bbox[0]),
            "y": int(bbox[1]),
            "width": int(bbox[2] - bbox[0]),
            "height": int(bbox[3] - bbox[1])
        }
        
        return {
            "object_id": obj.object_id,
            "frame_id": obj.frame_id,
            "timestamp": obj.time_stamp.isoformat(),
            "image_filename": image_filename,
            "preview_filename": preview_filename,
            "bounding_box": pixel_bbox,
            "confidence": float(obj.track.confidence),
            "class_id": obj.class_id,
            "class_name": self._get_class_name(obj.class_id),
            "source_id": obj.source_id,
            "track_id": obj.track.track_id,
            "global_id": getattr(obj, 'global_id', None)
        }
    
    def create_lost_object_data(self, obj, image_width: int, image_height: int,
                               image_filename: str, preview_filename: str) -> Dict[str, Any]:
        """
        Create object data dictionary for lost objects.
        
        Args:
            obj: ObjectResult object
            image_width: Width of the image
            image_height: Height of the image
            image_filename: Name of the saved image file
            preview_filename: Name of the saved preview file
            
        Returns:
            Dictionary with object data in labeling format
        """
        # Use absolute pixel coordinates for COCO compatibility
        bbox = obj.track.bounding_box
        pixel_bbox = {
            "x": int(bbox[0]),
            "y": int(bbox[1]),
            "width": int(bbox[2] - bbox[0]),
            "height": int(bbox[3] - bbox[1])
        }
        
        return {
            "object_id": obj.object_id,
            "frame_id": obj.frame_id,
            "detected_timestamp": obj.time_detected.isoformat(),
            "lost_timestamp": obj.time_lost.isoformat(),
            "image_filename": image_filename,
            "preview_filename": preview_filename,
            "bounding_box": pixel_bbox,
            "confidence": float(obj.track.confidence),
            "class_id": obj.class_id,
            "class_name": self._get_class_name(obj.class_id),
            "source_id": obj.source_id,
            "track_id": obj.track.track_id,
            "global_id": getattr(obj, 'global_id', None),
            "lost_frames": obj.lost_frames
        }
    
    def _get_class_name(self, class_id: int) -> str:
        """
        Get class name from class ID.
        
        Args:
            class_id: Class ID
            
        Returns:
            Class name string
        """
        # Default COCO classes (can be extended or made configurable)
        coco_classes = [
            "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
            "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
            "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
            "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
            "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
            "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
            "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake",
            "chair", "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop",
            "mouse", "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
            "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush"
        ]
        
        if 0 <= class_id < len(coco_classes):
            return coco_classes[class_id]
        else:
            return f"class_{class_id}"
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about saved labels.
        
        Returns:
            Dictionary with statistics
        """
        found_data = self._load_json(self.found_labels_file)
        lost_data = self._load_json(self.lost_labels_file)
        
        return {
            "found_objects": len(found_data.get("objects", [])),
            "lost_objects": len(lost_data.get("objects", [])),
            "total_objects": len(found_data.get("objects", [])) + len(lost_data.get("objects", [])),
            "found_labels_file": self.found_labels_file,
            "lost_labels_file": self.lost_labels_file,
            "date": self.date_str
        }
    
    def export_labels_for_training(self, output_dir: str = None) -> str:
        """
        Export labels in a format suitable for training.
        
        Args:
            output_dir: Output directory for training format
            
        Returns:
            Path to exported training data
        """
        if output_dir is None:
            output_dir = os.path.join(self.base_dir, 'training_data')
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Load current data
        found_data = self._load_json(self.found_labels_file)
        lost_data = self._load_json(self.lost_labels_file)
        
        # Combine all objects
        all_objects = found_data.get("objects", []) + lost_data.get("objects", [])
        
        # Create training format
        training_data = {
            "metadata": {
                "version": "1.0",
                "exported": datetime.datetime.now().isoformat(),
                "total_objects": len(all_objects),
                "found_objects": len(found_data.get("objects", [])),
                "lost_objects": len(lost_data.get("objects", []))
            },
            "objects": all_objects
        }
        
        # Save training data
        training_file = os.path.join(output_dir, f'{self.date_str}_training_labels.json')
        self._save_json(training_file, training_data)
        
        return training_file
    
    def _save_worker(self):
        """Background worker for periodic saving."""
        while self.running:
            time.sleep(1)  # Check every second
            
            current_time = time.time()
            if current_time - self.last_save_time > self.save_interval:
                self._save_all_buffers()
                self.last_save_time = current_time
    
    def _save_all_buffers(self):
        """Save all buffers (found and lost objects)."""
        self._save_found_buffer()
        self._save_lost_buffer()
    
    def flush_buffers(self):
        """Force save all buffered data."""
        self._save_all_buffers()
    
    def stop(self):
        """Stop the labeling manager and save any remaining data."""
        self.running = False
        self.flush_buffers()
        
        # Wait for save thread to finish
        if self.save_thread.is_alive():
            self.save_thread.join(timeout=5)
