from .object_detection_base import ModelBasedDetectorBase
from ..core.base_class import EvilEyeBase
from ..core.logger import get_module_logger

# Determine whether RF-DETR should be registered on this platform
_logger = get_module_logger("object_detection_rfdetr")
_SUPPORT_RFDETR = True
try:
    import torch  # noqa: F401
    from packaging import version
    torch_version = None
    try:
        import torch
        torch_version = version.parse(getattr(torch, "__version__", "0.0.0"))
    except Exception:
        torch_version = version.parse("0.0.0")
    if torch_version < version.parse("2.2.0"):
        _logger.info(f"RF-DETR disabled: requires torch>=2.2.0, found {torch_version}")
        _SUPPORT_RFDETR = False
except Exception:
    # If torch import fails, disable RF-DETR
    _logger.info("RF-DETR disabled: PyTorch not available")
    _SUPPORT_RFDETR = False


class ObjectDetectorRfdetr(ModelBasedDetectorBase):
    """RF-DETR-based object detector."""

    def __init__(self):
        super().__init__()
        self.model_name = "rfdetr-nano"

    def _get_detection_thread_type(self) -> str:
        return "rfdetr"

    def _get_default_model_name(self) -> str:
        return "rfdetr-nano"

    def _resolve_model_path(self, model_name: str) -> str:
        """RF-DETR uses model name as identifier, not file path."""
        return model_name

# Apply registration only if supported
if _SUPPORT_RFDETR:
    ObjectDetectorRfdetr = EvilEyeBase.register("ObjectDetectorRfdetr")(ObjectDetectorRfdetr)
else:
    _logger.info("ObjectDetectorRfdetr not registered due to environment constraints")
