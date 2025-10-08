import cv2
import os
from typing import Dict, Any, Optional
from ..core.pipeline_simple import PipelineSimple
from ..capture.video_capture_base import CaptureImage
from ..capture.video_capture_opencv import VideoCaptureOpencv
from ..object_tracker.tracking_results import TrackingResultList


class PipelineCapture(PipelineSimple):
    """
    Simple pipeline for capturing video from a single file.
    Returns captured frames for processing.
    """
    
    def __init__(self):
        super().__init__()
        self.source_config = {}
        self.video_capture = None
        self.frame_width = 0
        self.frame_height = 0
        self.total_frames = 0
        self._final_results_name = "output"

    def set_params_impl(self):
        """Set pipeline parameters from config"""
        super().set_params_impl()
        
        # Get video file path from config
        sources_config = self.params.get('sources', [])
        if sources_config and len(sources_config) > 0:
            self.source_config = sources_config[0]
        else:
            self.source_config = {}

    def init_impl(self, **kwargs):
        """Initialize video capture"""
        # Get video path from source config
        video_path = self.source_config.get('camera', '')
        if not video_path or not os.path.exists(video_path):
            self.logger.error(f"Error: Video file not found: {video_path}")
            return False
        
        # Create VideoCaptureOpencv and use source config directly
        self.video_capture = VideoCaptureOpencv()
        #self.video_capture.params = self.source_config
        
        # Set parameters and initialize video capture
        self.video_capture.set_params(**self.source_config)
        if not self.video_capture.init():
            self.logger.error(f"Error: Failed to initialize video capture: {video_path}")
            return False
        
        # Get video properties
        self.frame_width = int(self.video_capture.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_height = int(self.video_capture.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.total_frames = int(self.video_capture.capture.get(cv2.CAP_PROP_FRAME_COUNT))
        
        self.logger.info(f"Video initialized: {video_path}")
        self.logger.info(f"Resolution: {self.frame_width}x{self.frame_height}")
        self.logger.info(f"FPS: {self.video_capture.source_fps}")
        self.logger.info(f"Total frames: {self.total_frames}")
        
        return True

    def release_impl(self):
        """Release video capture resources"""
        if self.video_capture:
            self.video_capture.release()
            self.video_capture = None

    def start_impl(self):
        """Start video capture"""
        if self.video_capture:
            self.video_capture.start()
            self.logger.info("Video capture started")

    def stop_impl(self):
        """Stop video capture"""
        if self.video_capture:
            self.video_capture.stop()
        self.logger.info("Video capture stopped")

    def process_logic(self) -> Dict[str, Any]:
        """
        Capture and return next frame from video using VideoCaptureOpencv.get() method.
        
        Returns:
            Dictionary with frame data and metadata
        """
        results = {}
        results["sources"] = []
        results[self.get_final_results_name()] = []

        if not self.video_capture or not self.video_capture.is_opened():
            return results
        
        # Get frames from VideoCaptureOpencv using the get() method
        captured_images = self.video_capture.get()
        
        if not captured_images:
            # No frames available or end of video
            return results

        results["sources"] = captured_images

        # ToDo: process frames here

        # Produce dummy results
        processed_results = []
        for frame in captured_images:
            frame_res = TrackingResultList()
            frame_res.frame_id = frame.frame_id
            frame_res.source_id = frame.source_id
            frame_res.time_stamp = frame.time_stamp
            processed_results.append((frame_res, frame))

        results[self.get_final_results_name()] = processed_results

        return results

    def check_all_sources_finished(self) -> bool:
        """
        Check if video has finished.
        
        Returns:
            True if video has finished, False otherwise
        """
        if not self.video_capture or not self.video_capture.is_opened():
            return True
        return self.video_capture.is_finished()

    def get_video_info(self) -> Dict[str, Any]:
        """
        Get video information.
        
        Returns:
            Dictionary with video properties
        """
        if not self.video_capture:
            return {
                'video_path': self.source_config.get('camera', ''),
                'frame_width': 0,
                'frame_height': 0,
                'fps': None,
                'total_frames': 0,
                'current_frame': 0,
                'progress': 0
            }
        
        return {
            'video_path': self.source_config.get('camera', ''),
            'frame_width': self.frame_width,
            'frame_height': self.frame_height,
            'fps': self.video_capture.source_fps,
            'total_frames': self.total_frames,
            'current_frame': self.video_capture.video_current_frame if hasattr(self.video_capture, 'video_current_frame') else 0,
            'progress': (self.video_capture.video_current_frame / self.total_frames) if self.total_frames > 0 and hasattr(self.video_capture, 'video_current_frame') else 0
        }

    def seek_frame(self, frame_number: int) -> bool:
        """
        Seek to specific frame number.
        
        Args:
            frame_number: Frame number to seek to
            
        Returns:
            True if seek successful, False otherwise
        """
        if not self.video_capture or not self.video_capture.is_opened():
            return False
        
        if 0 <= frame_number < self.total_frames:
            self.video_capture.capture.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            return True
        return False

    def generate_default_structure(self, num_sources: int):
        """
        Generate default configuration structure for video capture pipeline.
        
        Args:
            num_sources: Number of sources (should be 1 for video capture)
        """
        if num_sources != 1:
            self.logger.warning("Warning: PipelineCapture supports only 1 source")
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
        PipelineCapture returns a list with the current video capture object.
        
        Returns:
            List containing the current video capture object
        """
        if hasattr(self, 'video_capture') and self.video_capture is not None:
            return [self.video_capture]
        return []
