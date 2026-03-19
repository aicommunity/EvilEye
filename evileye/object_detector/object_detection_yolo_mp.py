from .object_detection_base import ModelBasedDetectorBase
from ..core.base_class import EvilEyeBase


@EvilEyeBase.register("ObjectDetectorYoloMp")
class ObjectDetectorYoloMp(ModelBasedDetectorBase):
    """YOLO multiprocessing-based object detector."""

    def __init__(self):
        super().__init__()
        self.model_name = "models/yolo11n.pt"

    def _get_detection_thread_type(self) -> str:
        return "yolo_mp"

    def _get_default_model_name(self) -> str:
        return "models/yolo11n.pt"
