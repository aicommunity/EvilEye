"""
Visualization adapter for connecting Visualizer to Controller through events.
"""

from typing import Dict, List, Any, Optional
import logging

from .interfaces import IVisualizationProvider
from ..core.logger import get_module_logger


class VisualizationAdapter(IVisualizationProvider):
    """
    Adapter that wraps Visualizer and implements IVisualizationProvider interface.
    
    This adapter allows Controller to use visualization without knowing about GUI details.
    """
    
    def __init__(self, visualizer=None, logger: Optional[logging.Logger] = None):
        """
        Initialize visualization adapter.
        
        Args:
            visualizer: Visualizer instance (can be None if created later)
            logger: Optional logger instance
        """
        self.visualizer = visualizer
        self.logger = logger or get_module_logger("visualization_adapter")
        self._initialized = False
    
    def set_visualizer(self, visualizer) -> None:
        """
        Set visualizer instance.
        
        Args:
            visualizer: Visualizer instance
        """
        self.visualizer = visualizer
        if visualizer:
            self._initialized = True
            self.logger.info("Visualizer set in adapter")
    
    def update(self, processing_frames: Dict[int, Any], 
               source_last_processed_frame_id: Dict[int, int],
               objects: List[Any], 
               dropped_frames: Dict[int, int],
               debug_info: Dict[str, Any]) -> None:
        """
        Update visualization with new frame data.
        
        Args:
            processing_frames: Dictionary mapping source_id to list of CaptureImage frames
                              OR list of CaptureImage frames (will be converted)
            source_last_processed_frame_id: Dictionary mapping source_id to last processed frame ID
            objects: List of ObjectResultList objects
            dropped_frames: Dictionary mapping source_id to dropped frame count
            debug_info: Debug information dictionary
        """
        if self.visualizer:
            try:
                # Convert processing_frames to format expected by visualizer.update()
                # visualizer.update() expects list[CaptureImage], not dict
                processing_frames_list = []
                if isinstance(processing_frames, dict):
                    # Convert dict to flat list
                    for source_id, frames in processing_frames.items():
                        if isinstance(frames, list):
                            processing_frames_list.extend(frames)
                        else:
                            processing_frames_list.append(frames)
                elif isinstance(processing_frames, list):
                    # Already a list
                    processing_frames_list = processing_frames
                
                # Convert dropped_frames to list format expected by visualizer
                # visualizer.update() expects list, but we might have dict[int, int]
                dropped_frames_list = dropped_frames
                if isinstance(dropped_frames, dict):
                    # Convert dict to list - visualizer expects list format
                    # For now, pass empty list if dict format (visualizer might not use it)
                    dropped_frames_list = []
                
                self.visualizer.update(
                    processing_frames_list,
                    source_last_processed_frame_id,
                    objects,
                    dropped_frames_list,
                    debug_info
                )
            except Exception as e:
                self.logger.error(f"Error updating visualizer: {e}", exc_info=True)
    
    def start(self) -> None:
        """Start visualization."""
        if self.visualizer:
            try:
                self.visualizer.start()
                self.logger.info("Visualizer started via adapter")
            except Exception as e:
                self.logger.error(f"Error starting visualizer: {e}", exc_info=True)
    
    def stop(self) -> None:
        """Stop visualization."""
        if self.visualizer:
            try:
                self.visualizer.stop()
                self.logger.info("Visualizer stopped via adapter")
            except Exception as e:
                self.logger.error(f"Error stopping visualizer: {e}", exc_info=True)
    
    def set_params(self, **params) -> None:
        """Set visualization parameters."""
        if self.visualizer:
            try:
                self.visualizer.set_params(**params)
            except Exception as e:
                self.logger.error(f"Error setting visualizer params: {e}", exc_info=True)
    
    def get_params(self) -> Dict[str, Any]:
        """Get current visualization parameters."""
        if self.visualizer:
            try:
                return self.visualizer.get_params()
            except Exception as e:
                self.logger.error(f"Error getting visualizer params: {e}", exc_info=True)
        return {}
    
    def is_available(self) -> bool:
        """Check if visualizer is available."""
        return self.visualizer is not None and self._initialized
    
    def set_current_main_widget_size(self, width: int, height: int) -> None:
        """Set main widget size for visualizer."""
        if self.visualizer and hasattr(self.visualizer, 'set_current_main_widget_size'):
            try:
                self.visualizer.set_current_main_widget_size(width, height)
            except Exception as e:
                self.logger.error(f"Error setting widget size: {e}", exc_info=True)
