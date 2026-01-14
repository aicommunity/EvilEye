"""
Event system for GUI communication.

Events are used to decouple the core system from GUI components.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from enum import Enum


class GUIEventType(Enum):
    """Types of GUI events."""
    FRAME_PROCESSED = "frame_processed"
    OBJECT_DETECTED = "object_detected"
    PROGRESS_UPDATE = "progress_update"
    INITIALIZATION_COMPLETE = "initialization_complete"
    INITIALIZATION_FAILED = "initialization_failed"
    VISUALIZATION_UPDATE = "visualization_update"
    ZONE_UPDATED = "zone_updated"
    ROI_UPDATED = "roi_updated"


@dataclass
class GUIEvent:
    """Base GUI event class."""
    event_type: GUIEventType
    data: Dict[str, Any]
    timestamp: Optional[float] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            import time
            self.timestamp = time.time()


@dataclass
class FrameProcessedEvent(GUIEvent):
    """Event emitted when a frame is processed."""
    def __init__(self, processing_frames: Dict[int, Any],
                 source_last_processed_frame_id: Dict[int, int],
                 objects: List[Any],
                 dropped_frames: Dict[int, int],
                 debug_info: Dict[str, Any]):
        super().__init__(
            event_type=GUIEventType.FRAME_PROCESSED,
            data={
                'processing_frames': processing_frames,
                'source_last_processed_frame_id': source_last_processed_frame_id,
                'objects': objects,
                'dropped_frames': dropped_frames,
                'debug_info': debug_info
            }
        )


@dataclass
class ProgressUpdateEvent(GUIEvent):
    """Event emitted for progress updates."""
    def __init__(self, value: int, stage_text: str):
        super().__init__(
            event_type=GUIEventType.PROGRESS_UPDATE,
            data={
                'value': value,
                'stage_text': stage_text
            }
        )


@dataclass
class InitializationCompleteEvent(GUIEvent):
    """Event emitted when initialization is complete."""
    def __init__(self, controller_instance: Any):
        super().__init__(
            event_type=GUIEventType.INITIALIZATION_COMPLETE,
            data={
                'controller': controller_instance
            }
        )


@dataclass
class InitializationFailedEvent(GUIEvent):
    """Event emitted when initialization fails."""
    def __init__(self, error_message: str):
        super().__init__(
            event_type=GUIEventType.INITIALIZATION_FAILED,
            data={
                'error_message': error_message
            }
        )


class GUIEventEmitter:
    """Simple event emitter for GUI events."""
    
    def __init__(self):
        self._listeners: Dict[GUIEventType, List[callable]] = {}
    
    def subscribe(self, event_type: GUIEventType, callback: callable) -> None:
        """Subscribe to an event type."""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)
    
    def unsubscribe(self, event_type: GUIEventType, callback: callable) -> None:
        """Unsubscribe from an event type."""
        if event_type in self._listeners:
            try:
                self._listeners[event_type].remove(callback)
            except ValueError:
                pass
    
    def emit(self, event: GUIEvent) -> None:
        """Emit an event to all subscribers."""
        if event.event_type in self._listeners:
            for callback in self._listeners[event.event_type]:
                try:
                    callback(event)
                except Exception as e:
                    # Log error but don't break event system
                    import logging
                    logger = logging.getLogger("gui_events")
                    logger.error(f"Error in event callback: {e}", exc_info=True)
    
    def clear(self) -> None:
        """Clear all listeners."""
        self._listeners.clear()
