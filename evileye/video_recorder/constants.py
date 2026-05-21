"""
Constants for video recorder module.
"""


class RecorderConstants:
    # Queue configuration
    DEFAULT_FRAME_QUEUE_SIZE: int = 100

    # Timestamp threshold for determining absolute vs relative timestamps
    TIMESTAMP_THRESHOLD_ABSOLUTE: float = 86400.0

    # Frame timing
    DEFAULT_FRAME_INTERVAL: float = 0.04
    DEFAULT_FPS: float = 25.0

    # File management
    MIN_FILE_AGE_SECONDS: int = 30

    # Thread timeout
    RECORDING_THREAD_JOIN_TIMEOUT: float = 5.0
