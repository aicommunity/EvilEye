from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .interfaces import IDatabaseAdapter, IEventDetector, IObjectHandler, IPipeline, IVisualizer


@dataclass(frozen=True)
class EventUpdate:
    """Serializable input contract for process-isolated event detectors.

    payload must contain only primitive mappings/sequences, strings, numbers,
    booleans, and None. Runtime objects such as handlers, frames, and locks
    must stay in the host process.
    """

    sequence: int
    kind: str
    payload: Mapping[str, Any]
    source_id: Optional[int] = None
    timestamp: Any = None

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
