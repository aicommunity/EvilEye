"""Spawn-safe GStreamer bootstrap for capture worker processes."""

from __future__ import annotations


def ensure_gstreamer_spawn_runtime() -> None:
    try:
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        if not Gst.is_initialized():
            Gst.init(None)
        import cv2  # noqa: F401
    except ImportError:
        pass
