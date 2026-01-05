"""
Interfaces for GUI components to interact with the core system.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IVisualizationProvider(ABC):
    """Interface for visualization components."""
    
    @abstractmethod
    def update(self, processing_frames: Dict[int, Any], 
               source_last_processed_frame_id: Dict[int, int],
               objects: List[Any], 
               dropped_frames: Dict[int, int],
               debug_info: Dict[str, Any]) -> None:
        """
        Update visualization with new frame data.
        
        Args:
            processing_frames: Dictionary mapping source_id to CaptureImage frames
            source_last_processed_frame_id: Dictionary mapping source_id to last processed frame ID
            objects: List of ObjectResultList objects
            dropped_frames: Dictionary mapping source_id to dropped frame count
            debug_info: Debug information dictionary
        """
        pass
    
    @abstractmethod
    def start(self) -> None:
        """Start visualization."""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Stop visualization."""
        pass
    
    @abstractmethod
    def set_params(self, **params) -> None:
        """Set visualization parameters."""
        pass
    
    @abstractmethod
    def get_params(self) -> Dict[str, Any]:
        """Get current visualization parameters."""
        pass


class IProgressReporter(ABC):
    """Interface for progress reporting."""
    
    @abstractmethod
    def report_progress(self, value: int, stage_text: str) -> None:
        """
        Report initialization progress.
        
        Args:
            value: Progress value (0-100)
            stage_text: Description of current stage
        """
        pass


class IGUIEventHandler(ABC):
    """Interface for handling GUI events."""
    
    @abstractmethod
    def handle_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """
        Handle GUI-related event.
        
        Args:
            event_type: Type of event
            event_data: Event data dictionary
        """
        pass
