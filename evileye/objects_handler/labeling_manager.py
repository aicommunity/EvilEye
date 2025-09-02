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
    
    def __init__(self, base_dir: str = 'EvilEyeData', cameras_params: list = None):
        """
        Initialize the labeling manager.
        
        Args:
            base_dir: Base directory for saving labels and images
            cameras_params: List of camera parameters for source name mapping
        """
        self.base_dir = base_dir
        self.images_dir = os.path.join(base_dir, 'images')
        self.cameras_params = cameras_params or []
        
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
        
        # Pre-load existing data into buffers to avoid clearing files
        self._preload_existing_data()
        
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
                data = json.load(f)
                # Ensure the data has the required structure
                if not isinstance(data, dict):
                    data = {}
                if "metadata" not in data:
                    data["metadata"] = {
                        "version": "1.0",
                        "created": datetime.datetime.now().isoformat(),
                        "description": "Object detection labels",
                        "total_objects": 0
                    }
                if "objects" not in data:
                    data["objects"] = []
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            # Return default structure if file doesn't exist or is corrupted
            return {
                "metadata": {
                    "version": "1.0",
                    "created": datetime.datetime.now().isoformat(),
                    "description": "Object detection labels",
                    "total_objects": 0
                },
                "objects": []
            }
    
    def _save_json(self, file_path: str, data: Dict[str, Any]):
        """Save JSON file safely."""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving JSON file {file_path}: {e}")
    
    def _update_metadata(self, data: Dict[str, Any], total_objects: int):
        """Update metadata in label data."""
        # Ensure metadata exists
        if "metadata" not in data:
            data["metadata"] = {
                "version": "1.0",
                "created": datetime.datetime.now().isoformat(),
                "description": "Object detection labels",
                "total_objects": 0
            }
        
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
            
            # Ensure objects list exists
            if "objects" not in data:
                data["objects"] = []
            
            # Check for duplicates before adding
            existing_timestamps = {obj.get('timestamp') for obj in data["objects"]}
            existing_ids = {obj.get('object_id') for obj in data["objects"]}
            new_objects = []
            
            for obj in self.found_buffer:
                if obj.get('timestamp') not in existing_timestamps or obj.get('object_id') not in existing_ids:
                    new_objects.append(obj)
                else:
                    print(f"Skipping duplicate found object with timestamp: {obj.get('timestamp')} for object: {obj.get('object_id')}")
            
            # Add only new objects
            if new_objects:
                data["objects"].extend(new_objects)
                print(f"Saving {len(new_objects)} new found objects (total: {len(data['objects'])})")
            else:
                print(f"No new found objects to save")
            
            # Update metadata
            self._update_metadata(data, len(data["objects"]))
            
            # Save updated data
            try:
                self._save_json(self.found_labels_file, data)
                # Clear buffer only if save was successful
                self.found_buffer.clear()
            except Exception as e:
                print(f"Error saving found objects buffer: {e}")
    
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
            
            # Ensure objects list exists
            if "objects" not in data:
                data["objects"] = []
            
            # Check for duplicates before adding
            existing_timestamps = {obj.get('detected_timestamp') for obj in data["objects"]}
            existing_ids = {obj.get('object_id') for obj in data["objects"]}
            new_objects = []
            
            for obj in self.lost_buffer:
                if obj.get('detected_timestamp') not in existing_timestamps or obj.get('object_id') not in existing_ids:
                    new_objects.append(obj)
                else:
                    print(f"Skipping duplicate lost object with timestamp: {obj.get('detected_timestamp')} for object: {obj.get('object_id')}")
            
            # Add only new objects
            if new_objects:
                data["objects"].extend(new_objects)
                print(f"Saving {len(new_objects)} new lost objects (total: {len(data['objects'])})")
            else:
                print(f"No new lost objects to save")
            
            # Update metadata
            self._update_metadata(data, len(data["objects"]))
            
            # Save updated data
            try:
                self._save_json(self.lost_labels_file, data)
                # Clear buffer only if save was successful
                self.lost_buffer.clear()
            except Exception as e:
                print(f"Error saving lost objects buffer: {e}")
    
    def create_found_object_data(self, obj, image_width: int, image_height: int, 
                                image_filename: str, preview_filename: str) -> Dict[str, Any]:
        """
        Create object data dictionary for found objects.
        
        Args:
            obj: ObjectResult object
            image_width: Width of the image
            image_height: Height of the image
            image_filename: Name of the saved image file
            preview_filename: Name of the saved preview file (not used in labels)
            
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
        
        # Create relative path to image (without date folder)
        relative_image_path = os.path.join('detected_frames', image_filename)
        
        # Get source name from cameras params if available
        source_name = self._get_source_name(obj.source_id)
        
        return {
            "object_id": obj.object_id,
            "frame_id": obj.frame_id,
            "timestamp": obj.time_stamp.isoformat(),
            "image_filename": relative_image_path,
            "bounding_box": pixel_bbox,
            "confidence": float(obj.track.confidence),
            "class_id": obj.class_id,
            "class_name": self._get_class_name(obj.class_id),
            "source_id": obj.source_id,
            "source_name": source_name,
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
            preview_filename: Name of the saved preview file (not used in labels)
            
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
        
        # Create relative path to image (without date folder)
        relative_image_path = os.path.join('lost_frames', image_filename)
        
        # Get source name from cameras params if available
        source_name = self._get_source_name(obj.source_id)
        
        return {
            "object_id": obj.object_id,
            "frame_id": obj.frame_id,
            "detected_timestamp": obj.time_detected.isoformat(),
            "lost_timestamp": obj.time_lost.isoformat(),
            "image_filename": relative_image_path,
            "bounding_box": pixel_bbox,
            "confidence": float(obj.track.confidence),
            "class_id": obj.class_id,
            "class_name": self._get_class_name(obj.class_id),
            "source_id": obj.source_id,
            "source_name": source_name,
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
    
    def _get_source_name(self, source_id: int) -> str:
        """
        Get source name from source ID using cameras parameters.
        
        Args:
            source_id: Source ID
            
        Returns:
            Source name or default name if not found
        """
        for camera in self.cameras_params:
            if source_id in camera.get('source_ids', []):
                id_idx = camera['source_ids'].index(source_id)
                source_names = camera.get('source_names', [])
                if id_idx < len(source_names):
                    return source_names[id_idx]
        return f"camera_{source_id}"
    
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
    
    def _preload_existing_data(self):
        """Pre-load existing data from JSON files to avoid clearing them on startup."""
        try:
            print(f"🔄 Pre-loading existing data from {self.date_str}...")
            
            # Check and repair JSON files if needed
            self._check_and_repair_json_files()
            
            # Load found objects
            found_data = self._load_json(self.found_labels_file)
            existing_found = found_data.get("objects", [])
            if existing_found:
                print(f"📊 Found {len(existing_found)} existing found objects")
                # Don't add to buffer, just ensure file is preserved
            
            # Load lost objects
            lost_data = self._load_json(self.lost_labels_file)
            existing_lost = lost_data.get("objects", [])
            if existing_lost:
                print(f"📊 Found {len(existing_lost)} existing lost objects")
                # Don't add to buffer, just ensure file is preserved
            
            total_existing = len(existing_found) + len(existing_lost)
            if total_existing > 0:
                print(f"✅ Successfully pre-loaded {total_existing} existing objects")
            else:
                print(f"ℹ️ No existing objects found, starting fresh")
                
        except Exception as e:
            print(f"⚠️ Warning: Error pre-loading existing data: {e}")
            print(f"ℹ️ Continuing with fresh start")
    
    def _check_and_repair_json_files(self):
        """Check and repair corrupted JSON files."""
        try:
            # Check found objects file
            if os.path.exists(self.found_labels_file):
                try:
                    with open(self.found_labels_file, 'r', encoding='utf-8') as f:
                        json.load(f)
                    print(f"✅ Found objects file is valid")
                except json.JSONDecodeError as e:
                    print(f"⚠️ Found objects file is corrupted: {e}")
                    print(f"🔄 Attempting to repair...")
                    self._repair_json_file(self.found_labels_file, "found")
            
            # Check lost objects file
            if os.path.exists(self.lost_labels_file):
                try:
                    with open(self.lost_labels_file, 'r', encoding='utf-8') as f:
                        json.load(f)
                    print(f"✅ Lost objects file is valid")
                except json.JSONDecodeError as e:
                    print(f"⚠️ Lost objects file is corrupted: {e}")
                    print(f"🔄 Attempting to repair...")
                    self._repair_json_file(self.lost_labels_file, "lost")
                    
        except Exception as e:
            print(f"⚠️ Warning: Error checking JSON files: {e}")
    
    def _repair_json_file(self, file_path: str, file_type: str):
        """Attempt to repair a corrupted JSON file."""
        try:
            # Create backup of corrupted file
            backup_path = f"{file_path}.backup.{int(time.time())}"
            os.rename(file_path, backup_path)
            print(f"💾 Created backup: {backup_path}")
            
            # Create new valid file
            new_data = {
                "metadata": {
                    "version": "1.0",
                    "created": datetime.datetime.now().isoformat(),
                    "description": f"Object {file_type} labels (repaired)",
                    "total_objects": 0
                },
                "objects": []
            }
            
            self._save_json(file_path, new_data)
            print(f"✅ Repaired {file_type} objects file")
            
        except Exception as e:
            print(f"❌ Failed to repair {file_type} objects file: {e}")
            # Try to restore from backup
            try:
                if os.path.exists(backup_path):
                    os.rename(backup_path, file_path)
                    print(f"🔄 Restored original file from backup")
            except Exception as restore_e:
                print(f"❌ Failed to restore from backup: {restore_e}")
