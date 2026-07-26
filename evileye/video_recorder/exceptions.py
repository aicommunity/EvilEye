"""
Exception hierarchy for video recorder module.
"""


class RecorderError(Exception):
    """Base exception for all recorder-related errors."""


class RecorderInitializationError(RecorderError):
    """Raised when recorder initialization fails."""


class RecorderWriteError(RecorderError):
    """Raised when frame writing fails."""


class RecorderValidationError(RecorderError):
    """Raised when video file validation fails."""


class RecorderConfigurationError(RecorderError):
    """Raised when recorder configuration is invalid."""
