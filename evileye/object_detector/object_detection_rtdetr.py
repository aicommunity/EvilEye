from .object_detection_base import ModelBasedDetectorBase
from ..core.base_class import EvilEyeBase


@EvilEyeBase.register("ObjectDetectorRtdetr")
class ObjectDetectorRtdetr(ModelBasedDetectorBase):
    """RT-DETR-based object detector."""

    def __init__(self):
        super().__init__()
        self.model_name = "rtdetr-l.pt"

    def _get_detection_thread_type(self) -> str:
        return "rtdetr"

    def _get_default_model_name(self) -> str:
        return "rtdetr-l.pt"
