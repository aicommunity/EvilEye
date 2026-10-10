from .object_detection_base import ModelBasedDetectorBase
from ..core.base_class import EvilEyeBase
from ..core.plugins import register_module


@register_module(
    "ObjectDetectorYoloMp",
    kind="detector",
    capabilities=("legacy_processor_protocol",),
    execution_modes=("thread", "process"),
)
class ObjectDetectorYoloMp(ModelBasedDetectorBase):
    """Legacy YOLO detector that always uses MP detection threads.

    .. deprecated::
        Prefer :class:`ObjectDetectorYolo` with ``"execution_mode": "process"``
        in config. That path uses ``DetectionThreadYoloMp`` with restart policy
        and the same feed/drain contract without a separate registered type.
    """

    def __init__(self):
        super().__init__()
        self.model_name = "models/yolo11n.pt"

    def _get_detection_thread_type(self) -> str:
        return "yolo_mp"

    def _get_default_model_name(self) -> str:
        return "models/yolo11n.pt"
