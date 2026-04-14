from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class BatchMeta:
    payload_version: int
    source_id: Optional[int]
    frame_id: Optional[int]
    batch_age_ms: float
    is_partial: bool


def attach_frame_contract(frame: Any, payload_version: int = 1) -> Any:
    """Attach descriptor-friendly frame metadata without changing payload shape."""
    if frame is None:
        return frame
    try:
        setattr(frame, "payload_version", int(payload_version))
    except Exception:
        pass
    try:
        frame_ref = getattr(frame, "frame_handle", None)
        if frame_ref is not None:
            setattr(frame, "frame_ref", frame_ref)
    except Exception:
        pass
    return frame
