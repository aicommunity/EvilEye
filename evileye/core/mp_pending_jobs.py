"""Typed pending-job metadata for MP async feed/drain bridges."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .frame_transport import FrameHandle


@dataclass(frozen=True, slots=True)
class DetectorPendingJob:
    split_image: list
    capture_image: Any
    handles: list[FrameHandle]


@dataclass(frozen=True, slots=True)
class TrackerPendingJob:
    detections: Any
    frame_handle: FrameHandle | None
