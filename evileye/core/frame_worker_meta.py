"""Pack Frame metadata for MP worker IPC without getattr."""

from __future__ import annotations

import time
from typing import Any

from .frame import Frame


def frame_to_worker_meta(frame: Frame) -> dict[str, Any]:
    return {
        "source_id": frame.source_id,
        "frame_id": frame.frame_id,
        "time_stamp": frame.time_stamp,
        "current_video_frame": frame.current_video_frame,
        "current_video_position": frame.current_video_position,
        "source_video_duration": frame.source_video_duration,
    }


def pack_frame_for_worker(
    frame: Frame,
    *,
    frame_transport,
    detection_result: Any,
) -> tuple[dict, Any]:
    """Build worker dict payload and optional SHM handle."""
    image = frame.image
    if image is None:
        return {
            "detection_result": detection_result,
            "frame_handle": None,
            "frame_meta": frame_to_worker_meta(frame),
        }, None
    frame_handle = frame_transport.alloc_frame(
        image=image,
        frame_id=int(frame.frame_id or 0),
        timestamp=float(frame.time_stamp or time.time()),
    )
    return {
        "detection_result": detection_result,
        "frame_handle": frame_handle,
        "frame_meta": frame_to_worker_meta(frame),
    }, frame_handle
