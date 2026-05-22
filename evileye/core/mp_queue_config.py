"""Centralized MP/thread queue sizing (env EVILEYE_MP_QUEUE_SCALE)."""

from __future__ import annotations

import os

from ..object_detector.constants import (
    DEFAULT_INPUT_QUEUE_SIZE,
    DEFAULT_OUTPUT_QUEUE_SIZE,
    DEFAULT_THREAD_QUEUE_SIZE,
)


def env_scale() -> int:
    try:
        return max(1, int(os.getenv("EVILEYE_MP_QUEUE_SCALE", "1") or "1"))
    except (TypeError, ValueError):
        return 1


def detector_input_queue_size() -> int:
    return max(2, DEFAULT_INPUT_QUEUE_SIZE * env_scale())


def detector_thread_queue_size() -> int:
    return max(2, DEFAULT_THREAD_QUEUE_SIZE * env_scale())


def detector_output_queue_size() -> int:
    return max(4, DEFAULT_OUTPUT_QUEUE_SIZE * env_scale())


def mp_control_queue_size(roi_count: int, *, role: str) -> int:
    scale = env_scale()
    if role == "detector":
        return max(max(roi_count, 2), 2) * scale
    return max(4, 4 * scale)


def tracker_input_queue_size() -> int:
    return max(2, 2 * env_scale())


def tracker_output_queue_size() -> int:
    return max(4, 4 * env_scale())


def mp_drain_poll_sec() -> float:
    try:
        return float(os.getenv("EVILEYE_MP_DRAIN_POLL_SEC", "0.05") or "0.05")
    except (TypeError, ValueError):
        return 0.05


def mp_pending_cap_detector(roi_count: int) -> int:
    """FIFO depth cap for DetectionThreadYoloMp._mp_pending (not scaled by QUEUE_SCALE)."""
    override = os.getenv("EVILEYE_MP_PENDING_CAP", "").strip()
    if override:
        try:
            return max(1, int(override))
        except (TypeError, ValueError):
            pass
    return max(max(int(roi_count), 1), 2)


def mp_pending_cap_tracker() -> int:
    override = os.getenv("EVILEYE_MP_PENDING_CAP_TRACKER", "").strip()
    if override:
        try:
            return max(1, int(override))
        except (TypeError, ValueError):
            pass
    default = os.getenv("EVILEYE_MP_PENDING_CAP_TRACKER_DEFAULT", "4") or "4"
    try:
        return max(1, int(default))
    except (TypeError, ValueError):
        return 4
