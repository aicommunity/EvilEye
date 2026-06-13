"""
Exception hierarchy for video capture module.
"""


class CaptureError(Exception):
    """Base exception for all capture-related errors."""


class CaptureInitializationError(CaptureError):
    """Raised when capture initialization fails."""


class CaptureConnectionError(CaptureError):
    """Raised when connection to video source fails or is lost."""


class CaptureFrameError(CaptureError):
    """Raised when frame capture or processing fails."""


class CaptureConfigurationError(CaptureError):
    """Raised when capture configuration is invalid."""
