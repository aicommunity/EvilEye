import cv2
import os
from typing import Dict, Any, Optional
from ..core.pipeline_simple import PipelineSimple
from ..capture.video_capture_base import CaptureImage


class PipelineCapture(PipelineSimple):
    """
    Simple pipeline for capturing video from a single file.
    Returns captured frames for processing.
    """
    
    def __init__(self):
        super().__init__()
        self.video_path = ""
        self.cap = None
        self.frame_width = 0
        self.frame_height = 0
        self.fps = 30
        self.total_frames = 0
        self.current_frame = 0

    def set_params_impl(self):
        """Set pipeline parameters from config"""
        super().set_params_impl()
        
        # Get video file path from config
        sources_config = self.params.get('sources', [])
        if sources_config and len(sources_config) > 0:
            source_config = sources_config[0]
            # Try different possible field names for video path
            self.video_path = source_config.get('camera', source_config.get('source', ''))
            
            # Get video properties
            fps_config = source_config.get('fps', 30)
            if isinstance(fps_config, dict):
                self.fps = fps_config.get('value', 30)
            else:
                self.fps = fps_config

    def init_impl(self, **kwargs):
        """Initialize video capture"""
        if not self.video_path or not os.path.exists(self.video_path):
            print(f"Error: Video file not found: {self.video_path}")
            return False
        
        # Open video capture
        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            print(f"Error: Could not open video file: {self.video_path}")
            return False
        
        # Get video properties
        self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.current_frame = 0
        
        print(f"Video initialized: {self.video_path}")
        print(f"Resolution: {self.frame_width}x{self.frame_height}")
        print(f"FPS: {self.fps}")
        print(f"Total frames: {self.total_frames}")
        
        return True

    def release_impl(self):
        """Release video capture resources"""
        if self.cap:
            self.cap.release()
            self.cap = None

    def start_impl(self):
        """Start video capture"""
        if self.cap:
            self.current_frame = 0
            print("Video capture started")

    def stop_impl(self):
        """Stop video capture"""
        print("Video capture stopped")

    def process_logic(self) -> Dict[str, Any]:
        """
        Capture and return next frame from video.
        
        Returns:
            Dictionary with frame data and metadata
        """
        if not self.cap or not self.cap.isOpened():
            return {}
        
        # Read next frame
        ret, frame = self.cap.read()
        if not ret:
            # End of video
            return {}
        
        # Create capture image object
        capture_image = CaptureImage()
        capture_image.image = frame
        capture_image.width = self.frame_width
        capture_image.height = self.frame_height
        capture_image.current_video_position = self.current_frame
        capture_image.source_id = 0  # Single source
        
        # Prepare result
        result = {
            'source_id': 0,
            'frame_id': self.current_frame,
            'image': capture_image,
            'timestamp': self.current_frame / self.fps,  # Approximate timestamp
            'video_path': self.video_path,
            'frame_width': self.frame_width,
            'frame_height': self.frame_height,
            'fps': self.fps,
            'total_frames': self.total_frames,
            'progress': self.current_frame / self.total_frames if self.total_frames > 0 else 0
        }
        
        self.current_frame += 1
        return result

    def check_all_sources_finished(self) -> bool:
        """
        Check if video has finished.
        
        Returns:
            True if video has finished, False otherwise
        """
        if not self.cap or not self.cap.isOpened():
            return True
        return self.current_frame >= self.total_frames

    def get_video_info(self) -> Dict[str, Any]:
        """
        Get video information.
        
        Returns:
            Dictionary with video properties
        """
        return {
            'video_path': self.video_path,
            'frame_width': self.frame_width,
            'frame_height': self.frame_height,
            'fps': self.fps,
            'total_frames': self.total_frames,
            'current_frame': self.current_frame,
            'progress': self.current_frame / self.total_frames if self.total_frames > 0 else 0
        }

    def seek_frame(self, frame_number: int) -> bool:
        """
        Seek to specific frame number.
        
        Args:
            frame_number: Frame number to seek to
            
        Returns:
            True if seek successful, False otherwise
        """
        if not self.cap or not self.cap.isOpened():
            return False
        
        if 0 <= frame_number < self.total_frames:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            self.current_frame = frame_number
            return True
        return False

    def generate_default_structure(self, num_sources: int):
        """
        Generate default configuration structure for video capture pipeline.
        
        Args:
            num_sources: Number of sources (should be 1 for video capture)
        """
        if num_sources != 1:
            print("Warning: PipelineCapture supports only 1 source")
            num_sources = 1
        
        default_config = {
            "pipeline": {
                "pipeline_class": "PipelineCapture"
            },
            "sources": [
                {
                    "source": "path/to/video.mp4",
                    "fps": {
                        "value": 30
                    }
                }
            ]
        }
        
        return default_config

    def get_sources(self):
        """
        Get video sources for external subscriptions.
        PipelineCapture returns a list with the current capture object.
        
        Returns:
            List containing the current video capture object
        """
        if hasattr(self, 'cap') and self.cap is not None:
            return [self.cap]
        return []
