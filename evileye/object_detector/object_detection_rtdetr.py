from .object_detection_base import ModelBasedDetectorBase
from ..core.plugins import register_module
from .object_detection_yolo import ObjectDetectorYolo


@register_module(
    "ObjectDetectorRtdetr",
    kind="processor_item",
    capabilities=(
        "accepts_frame_handle",
        "model_class_mapping",
        "parallel_items",
    ),
    execution_modes=("thread", "process"),
    default_execution_mode="process",
)
class ObjectDetectorRtdetr(ObjectDetectorYolo):
    """RT-DETR detector using the same item contract as the YOLO detector."""

    def __init__(self):
        super().__init__()
        self.model_name = self._get_default_model_name()

    def _create_plugin_runtime(self):
        from .rtdetr_runtime import RtdetrRuntime

        return RtdetrRuntime(logger=self.logger)

    def _get_detection_thread_type(self) -> str:
        return "rtdetr"

    def _get_default_model_name(self) -> str:
        return "rtdetr-l.pt"

    def init_impl(self):
        # Preserve direct class usage; PluginRegistry uses the item adapter.
        return ModelBasedDetectorBase.init_impl(self)
