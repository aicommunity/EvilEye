"""
Constants and configuration for video capture module.

This module provides centralized constants and configuration classes
to replace magic numbers throughout the capture codebase.
"""

from dataclasses import dataclass
from typing import Optional


class CaptureConstants:
    """Constants for video capture operations.

    These constants are intentionally set to specific values based on
    performance and reliability requirements. Do not change without
    understanding the implications.
    """

    # Queue configuration
    # Intentionally small to avoid accumulating stale frames.
    # Better to drop frames than deliver old ones.
    DEFAULT_QUEUE_SIZE: int = 2
    # Frame buffer size for split streams in GStreamer
    # Increased from 2 to 5 to reduce buffer overflows and improve smoothness
    FRAME_BUFFER_SIZE: int = 5

    # Sleep intervals (in seconds)
    MIN_SLEEP_SECONDS: float = 0.001
    DEFAULT_SLEEP_SECONDS: float = 0.03

    # FPS multipliers for different source types
    FPS_MULTIPLIER_IP_CAMERA: float = 1.5
    FPS_MULTIPLIER_DEFAULT: float = 1.0

    # Timeout and monitoring intervals (in seconds)
    FRAME_TIMEOUT_SECONDS: float = 15.0
    RECONNECT_MONITOR_INTERVAL: float = 2.0
    INIT_GRACE_PERIOD_SECONDS: float = 5.0

    # Reconnection sleep intervals
    RECONNECT_SLEEP_SHORT: float = 0.1
    RECONNECT_SLEEP_LONG: float = 1.0

    # Default FPS fallback
    DEFAULT_FPS_FALLBACK: float = 15.0


@dataclass
class CaptureConfig:
    """Runtime configuration parameters for video capture."""

    queue_size: int = CaptureConstants.DEFAULT_QUEUE_SIZE
    min_sleep_seconds: float = CaptureConstants.MIN_SLEEP_SECONDS
    default_sleep_seconds: float = CaptureConstants.DEFAULT_SLEEP_SECONDS
    frame_timeout_seconds: float = CaptureConstants.FRAME_TIMEOUT_SECONDS
    reconnect_monitor_interval: float = CaptureConstants.RECONNECT_MONITOR_INTERVAL
    init_grace_period_seconds: float = CaptureConstants.INIT_GRACE_PERIOD_SECONDS
    default_fps_fallback: float = CaptureConstants.DEFAULT_FPS_FALLBACK

    @classmethod
    def from_dict(cls, config: Optional[dict]) -> "CaptureConfig":
        if not config:
            return cls()

        return cls(
            queue_size=config.get("queue_size", CaptureConstants.DEFAULT_QUEUE_SIZE),
            min_sleep_seconds=config.get("min_sleep_seconds", CaptureConstants.MIN_SLEEP_SECONDS),
            default_sleep_seconds=config.get("default_sleep_seconds", CaptureConstants.DEFAULT_SLEEP_SECONDS),
            frame_timeout_seconds=config.get("frame_timeout_seconds", CaptureConstants.FRAME_TIMEOUT_SECONDS),
            reconnect_monitor_interval=config.get("reconnect_monitor_interval", CaptureConstants.RECONNECT_MONITOR_INTERVAL),
            init_grace_period_seconds=config.get("init_grace_period_seconds", CaptureConstants.INIT_GRACE_PERIOD_SECONDS),
            default_fps_fallback=config.get("default_fps_fallback", CaptureConstants.DEFAULT_FPS_FALLBACK),
        )

