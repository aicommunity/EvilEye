from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
import numpy as np


@dataclass
class BoundingBox:
    """Унифицированный класс для bounding box"""
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float = 0.0
    class_id: Optional[int] = None
    
    @property
    def width(self) -> float:
        return self.x2 - self.x1
    
    @property
    def height(self) -> float:
        return self.y2 - self.y1
    
    @property
    def area(self) -> float:
        return self.width * self.height
    
    def to_list(self) -> List[float]:
        return [self.x1, self.y1, self.x2, self.y2]
    
    @classmethod
    def from_list(cls, bbox: List[float], confidence: float = 0.0, class_id: Optional[int] = None):
        return cls(bbox[0], bbox[1], bbox[2], bbox[3], confidence, class_id)


@dataclass
class Track:
    """Унифицированный класс для трека объекта"""
    track_id: int
    bounding_box: BoundingBox
    confidence: float = 0.0
    class_id: Optional[int] = None
    global_id: Optional[int] = None
    life_time: float = 0.0
    frame_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Frame:
    """Унифицированный класс для кадра"""
    id: int
    source_id: int
    timestamp: datetime
    data: np.ndarray
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def height(self) -> int:
        return self.data.shape[0]
    
    @property
    def width(self) -> int:
        return self.data.shape[1]
    
    @property
    def channels(self) -> int:
        return self.data.shape[2] if len(self.data.shape) > 2 else 1


@dataclass
class DetectionResult:
    """Унифицированный класс для результатов детекции"""
    frame_id: int
    source_id: int
    timestamp: datetime
    detections: List[BoundingBox]
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __len__(self) -> int:
        return len(self.detections)
    
    def filter_by_confidence(self, threshold: float) -> 'DetectionResult':
        filtered_detections = [
            det for det in self.detections 
            if det.confidence >= threshold
        ]
        return DetectionResult(
            frame_id=self.frame_id,
            source_id=self.source_id,
            timestamp=self.timestamp,
            detections=filtered_detections,
            metadata=self.metadata
        )


@dataclass
class TrackingResult:
    """Унифицированный класс для результатов трекинга"""
    frame_id: int
    source_id: int
    timestamp: datetime
    tracks: List[Track]
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __len__(self) -> int:
        return len(self.tracks)
    
    def get_track_by_id(self, track_id: int) -> Optional[Track]:
        for track in self.tracks:
            if track.track_id == track_id:
                return track
        return None
    
    def filter_active_tracks(self, min_life_time: float = 0.0) -> 'TrackingResult':
        active_tracks = [
            track for track in self.tracks 
            if track.life_time >= min_life_time
        ]
        return TrackingResult(
            frame_id=self.frame_id,
            source_id=self.source_id,
            timestamp=self.timestamp,
            tracks=active_tracks,
            metadata=self.metadata
        )
