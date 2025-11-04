from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any

from evileye.video_recorder.recording_params import RecordingParams


@dataclass
class SourceMeta:
    source_name: str
    source_address: Optional[str]
    source_type: Optional[str]
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    username: Optional[str] = None
    password: Optional[str] = None
    source_names: Optional[list[str]] = None  # All source names (for split sources)
    source_ids: Optional[list[int]] = None  # All source IDs (for split sources)


class VideoRecorderBase(ABC):
    """Abstract base for concrete recorders (GStreamer/OpenCV)."""

    def __init__(self) -> None:
        self.params: RecordingParams = RecordingParams()
        self.source: Optional[SourceMeta] = None
        self.is_running: bool = False

    @abstractmethod
    def start(self, source_meta: SourceMeta, params: RecordingParams) -> None:
        ...

    @abstractmethod
    def rotate_segment(self) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        ...


