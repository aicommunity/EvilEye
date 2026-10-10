"""Spawn-safe GStreamer bootstrap for capture worker processes."""

from __future__ import annotations


def initialize_gstreamer() -> None:
    """Initialize Gst without importing GUI or OpenCV libraries."""
    try:
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        if not Gst.is_initialized():
            Gst.init(None)
    except ImportError:
        pass


def ensure_gstreamer_spawn_runtime() -> None:
    """Initialize Gst before OpenCV in capture worker processes."""
    initialize_gstreamer()
    try:
        import cv2  # noqa: F401
    except ImportError:
        pass
