"""Compatibility class for the former separate YOLO multiprocessing module."""

from .object_detection_yolo import ObjectDetectorYolo


class ObjectDetectorYoloMp(ObjectDetectorYolo):
    """Import-compatible name for ``ObjectDetectorYolo``.

    Plugin configurations using ``type: ObjectDetectorYoloMp`` resolve through
    the registry alias to the canonical YOLO module. The configured
    ``execution_mode`` selects the thread or process runtime.
    """
