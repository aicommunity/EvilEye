"""
EvilEye - Intelligence video surveillance system

A comprehensive video surveillance system with object detection, tracking,
and multi-camera support.
"""

__version__ = "1.0.0"
__author__ = "EvilEye Team"
__email__ = "team@evileye.com"

from .core import Pipeline, ProcessorBase, ProcessorSource, ProcessorFrame, ProcessorStep
from .pipelines import PipelineSurveillance

# Import registered classes to ensure they are available
from .capture import video_capture
from .object_detector import object_detection_yolo
from .object_tracker import object_tracking_botsort
from .object_multi_camera_tracker import ObjectMultiCameraTracking

__all__ = [
    "Pipeline",
    "ProcessorBase", 
    "ProcessorSource",
    "ProcessorFrame",
    "ProcessorStep",
    "PipelineSurveillance",
]
