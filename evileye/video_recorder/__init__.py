"""Video recording package for EvilEye.

Contains implementations for recording raw input streams with minimal resource
usage. Prefer muxing/copy via GStreamer when available; otherwise fall back to
OpenCV re-encoding.
"""

from .constants import RecorderConstants
from .path_generator import PathGenerator
from .writer_factory import VideoWriterFactory
from .file_validator import FileValidator
from .exceptions import (
    RecorderError,
    RecorderInitializationError,
    RecorderWriteError,
    RecorderValidationError,
    RecorderConfigurationError
)
from .exceptions import (
    RecorderError,
    RecorderInitializationError,
    RecorderWriteError,
    RecorderValidationError,
    RecorderConfigurationError
)

__all__ = [
    "recording_params",
    "VideoValidator",
    "RecorderConstants",
    "PathGenerator",
    "VideoWriterFactory",
    "FileValidator",
    "RecorderError",
    "RecorderInitializationError",
    "RecorderWriteError",
    "RecorderValidationError",
    "RecorderConfigurationError",
]


