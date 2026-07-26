"""Shared imports for GStreamer capture mixin modules."""

from __future__ import annotations

import datetime
import threading
import time
from collections import deque
from queue import Empty, Full, Queue
from typing import Any, List, Optional, Tuple

import numpy as np

try:
    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst, GLib

    if not Gst.is_initialized():
        Gst.init(None)
except ImportError:
    Gst = None
    GLib = None

from .constants import CaptureConstants
from .exceptions import CaptureConnectionError, CaptureInitializationError
from .video_capture_base import CaptureDeviceType, EXEC_MODE_PROCESS
from ..core.frame import CaptureImage, Frame

from evileye.video_recorder.continuous_recorder_gst import GstContinuousRecorder
from evileye.video_recorder.recorder_base import SourceMeta

__all__ = [
    "Any",
    "CaptureConnectionError",
    "CaptureConstants",
    "CaptureDeviceType",
    "CaptureImage",
    "CaptureInitializationError",
    "Empty",
    "EXEC_MODE_PROCESS",
    "Frame",
    "Full",
    "GLib",
    "Gst",
    "GstContinuousRecorder",
    "List",
    "Optional",
    "Queue",
    "SourceMeta",
    "Tuple",
    "datetime",
    "deque",
    "np",
    "threading",
    "time",
]
