"""Public lazy exports for object detection and background-subtraction modules."""

from importlib import import_module as _import_module

_EXPORTS = {
    "BackgroundSubtractorBase": (".background_subtraction_base", "BackgroundSubtractorBase"),
    "BackgroundSubtractorMOG2": (".background_subtraction_gmm", "BackgroundSubtractorMOG2"),
    "DetectionResult": (".object_detection_base", "DetectionResult"),
    "DetectionResultList": (".object_detection_base", "DetectionResultList"),
    "ModelBasedDetectorBase": (".object_detection_base", "ModelBasedDetectorBase"),
    "ObjectDetectorBase": (".object_detection_base", "ObjectDetectorBase"),
    "ObjectDetectorYolo": (".object_detection_yolo", "ObjectDetectorYolo"),
    "ObjectDetectorYoloMp": (".object_detection_yolo_mp", "ObjectDetectorYoloMp"),
    "ObjectDetectorRfdetr": (".object_detection_rfdetr", "ObjectDetectorRfdetr"),
    "ObjectDetectorRtdetr": (".object_detection_rtdetr", "ObjectDetectorRtdetr"),
    "DetectionThreadBase": (".detection_thread_base", "DetectionThreadBase"),
    "DetectionThreadYolo": (".detection_thread_yolo", "DetectionThreadYolo"),
    "DetectionThreadYoloMp": (".detection_thread_yolo_mp", "DetectionThreadYoloMp"),
    "DetectionThreadRfdetr": (".detection_thread_rfdetr", "DetectionThreadRfdetr"),
    "DetectionThreadRtdetr": (".detection_thread_rtdetr", "DetectionThreadRtdetr"),
    "DetectionThreadFactory": (".detection_thread_factory", "DetectionThreadFactory"),
    "DEFAULT_CONFIDENCE": (".constants", "DEFAULT_CONFIDENCE"),
    "DEFAULT_INFERENCE_SIZE": (".constants", "DEFAULT_INFERENCE_SIZE"),
    "DEFAULT_INPUT_QUEUE_SIZE": (".constants", "DEFAULT_INPUT_QUEUE_SIZE"),
    "DEFAULT_NUM_DETECTION_THREADS": (".constants", "DEFAULT_NUM_DETECTION_THREADS"),
    "DEFAULT_STRIDE": (".constants", "DEFAULT_STRIDE"),
    "DEFAULT_THREAD_QUEUE_SIZE": (".constants", "DEFAULT_THREAD_QUEUE_SIZE"),
    "DetectorConfig": (".config", "DetectorConfig"),
    "InferenceParams": (".config", "InferenceParams"),
}

_BUILTIN_MODULES = (
    ".background_subtraction_base",
    ".background_subtraction_gmm",
    ".object_detection_base",
    ".object_detection_yolo",
    ".object_detection_yolo_mp",
    ".object_detection_rfdetr",
    ".object_detection_rtdetr",
    ".detection_thread_base",
    ".detection_thread_yolo",
    ".detection_thread_yolo_mp",
    ".detection_thread_rfdetr",
    ".detection_thread_rtdetr",
    ".detection_thread_factory",
    ".constants",
    ".config",
)

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = _import_module(module_name, __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))


def register_builtin_modules() -> None:
    """Import builtin detector modules explicitly for application startup."""
    for module_name in _BUILTIN_MODULES:
        _import_module(module_name, __name__)
