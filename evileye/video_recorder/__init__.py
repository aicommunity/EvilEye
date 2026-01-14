"""Video recording package for EvilEye.

Contains implementations for recording raw input streams with minimal resource
usage. Prefer muxing/copy via GStreamer when available; otherwise fall back to
OpenCV re-encoding.
"""

__all__ = [
    "recording_params",
    "VideoValidator",
]


