from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, ClassVar, Dict, List, Mapping, Optional, Sequence

from .interfaces import IDatabaseAdapter, IEventDetector, IObjectHandler, IPipeline, IVisualizer


@dataclass(frozen=True)
class EventFrameSnapshot:
    """Bounded JPEG attachment carried with a process event update."""

    source_id: int
    frame_id: int | None
    timestamp: Any
    current_video_position: Any
    jpeg_bytes: bytes
    MAX_BYTES: ClassVar[int] = 2 * 1024 * 1024
    _image_cache: Any = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, int) or isinstance(self.source_id, bool):
            raise TypeError("EventFrameSnapshot.source_id must be an integer")
        if self.frame_id is not None and (
            not isinstance(self.frame_id, int) or isinstance(self.frame_id, bool)
        ):
            raise TypeError("EventFrameSnapshot.frame_id must be an integer or None")
        if not isinstance(self.jpeg_bytes, bytes) or not self.jpeg_bytes:
            raise TypeError("EventFrameSnapshot.jpeg_bytes must be non-empty bytes")
        if len(self.jpeg_bytes) > self.MAX_BYTES:
            raise ValueError(
                f"EventFrameSnapshot exceeds the {self.MAX_BYTES}-byte frame limit"
            )

    @property
    def image(self):
        """Decode JPEG pixels on demand and cache them in this process."""
        if self._image_cache is None:
            import cv2
            import numpy as np

            image = cv2.imdecode(
                np.frombuffer(self.jpeg_bytes, dtype=np.uint8),
                cv2.IMREAD_COLOR,
            )
            if image is None or image.size == 0:
                raise ValueError("EventFrameSnapshot contains an invalid JPEG")
            object.__setattr__(self, "_image_cache", image)
        return self._image_cache

    def to_capture_image(self):
        """Expose the snapshot through the regular Frame-compatible shape."""
        from .frame import CaptureImage

        frame = CaptureImage()
        frame.source_id = self.source_id
        frame.frame_id = self.frame_id
        frame.time_stamp = self.timestamp
        frame.current_video_position = self.current_video_position
        frame.image = self.image
        return frame

    def __getstate__(self):
        return (
            self.source_id,
            self.frame_id,
            self.timestamp,
            self.current_video_position,
            self.jpeg_bytes,
        )

    def __setstate__(self, state):
        (
            source_id,
            frame_id,
            timestamp,
            current_video_position,
            jpeg_bytes,
        ) = state
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "frame_id", frame_id)
        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "current_video_position", current_video_position)
        object.__setattr__(self, "jpeg_bytes", jpeg_bytes)
        object.__setattr__(self, "_image_cache", None)


@dataclass(frozen=True)
class EventUpdate:
    """Serializable input contract for process-isolated event detectors.

    payload must contain only JSON-compatible values. Optional frame attachments
    contain bounded JPEG bytes; live handlers, frame buffers, and locks stay in
    the host process.
    """

    sequence: int
    kind: str
    payload: Mapping[str, Any]
    source_id: Optional[int] = None
    timestamp: Any = None
    frames: tuple[EventFrameSnapshot, ...] = ()
    MAX_FRAME_COUNT: ClassVar[int] = 16
    MAX_FRAME_BYTES: ClassVar[int] = 4 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("EventUpdate.sequence must be non-negative")
        if not str(self.kind).strip():
            raise ValueError("EventUpdate.kind must not be empty")
        if not isinstance(self.payload, Mapping):
            raise TypeError("EventUpdate.payload must be a mapping")
        try:
            json.dumps(dict(self.payload), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "EventUpdate.payload must contain only JSON-compatible values"
            ) from exc
        if self.source_id is not None and (
            not isinstance(self.source_id, int) or isinstance(self.source_id, bool)
        ):
            raise TypeError("EventUpdate.source_id must be an integer or None")
        frames = tuple(self.frames or ())
        if len(frames) > self.MAX_FRAME_COUNT:
            raise ValueError(
                f"EventUpdate contains more than {self.MAX_FRAME_COUNT} frame attachments"
            )
        if any(not isinstance(frame, EventFrameSnapshot) for frame in frames):
            raise TypeError("EventUpdate.frames must contain EventFrameSnapshot values")
        total_frame_bytes = sum(len(frame.jpeg_bytes) for frame in frames)
        if total_frame_bytes > self.MAX_FRAME_BYTES:
            raise ValueError(
                f"EventUpdate frame attachments exceed the {self.MAX_FRAME_BYTES}-byte limit"
            )
        object.__setattr__(self, "frames", frames)

    def get_frame(self, frame_index: int) -> EventFrameSnapshot | None:
        if not isinstance(frame_index, int) or isinstance(frame_index, bool):
            return None
        if frame_index < 0 or frame_index >= len(self.frames):
            return None
        return self.frames[frame_index]


@dataclass(frozen=True)
class PipelineConfig:
    """Контракт конфигурации для pipeline-слоя."""

    raw_config: Mapping[str, Any]
    credentials: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class DatabaseConfig:
    """Контракт конфигурации БД/JSON-хранилища."""

    params: Mapping[str, Any]
    adapters_params: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True)
class EventsConfig:
    """Контракт конфигурации системы детекторов событий."""

    detectors_params: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True)
class VisualizationConfig:
    """Контракт конфигурации визуализации."""

    visualizer_params: Mapping[str, Any]


@dataclass
class ControllerContext:
    """Минимальный контекст, который могут использовать сервисы контроллера.

    Это помогает не тянуть весь Controller в зависимости сервисов.
    """

    pipeline: Optional[IPipeline] = None
    objects_handler: Optional[IObjectHandler] = None
    events_detectors: List[IEventDetector] | None = None
    db_adapters: List[IDatabaseAdapter] | None = None
    visualizer: Optional[IVisualizer] = None


@dataclass
class PipelineDependencies:
    """Зависимости для инициализации/запуска pipeline."""

    config: PipelineConfig


@dataclass
class DatabaseDependencies:
    """Зависимости для инициализации БД и адаптеров."""

    config: DatabaseConfig


@dataclass
class EventsDependencies:
    """Зависимости для инициализации детекторов событий."""

    config: EventsConfig
    objects_handler: IObjectHandler


@dataclass
class VisualizationDependencies:
    """Зависимости для инициализации визуализатора."""

    config: VisualizationConfig
    pipeline: IPipeline
    objects_handler: IObjectHandler
