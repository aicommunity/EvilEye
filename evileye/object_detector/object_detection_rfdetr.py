import os
from .object_detection_base import ObjectDetectorBase
from .detection_thread_rfdetr import DetectionThreadRfdetr
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


class ObjectDetectorRfdetr(ObjectDetectorBase):
    id_cnt = 0  # Переменная для присвоения каждому детектору своего идентификатора

    def __init__(self):
        super().__init__()
        self.model_name = "rfdetr-nano"  # По умолчанию используем nano версию

    def init_impl(self):
        super().init_impl()
        self.detection_threads = []
        inf_params = {"show": self.params.get('show', False), 'conf': self.params.get('conf', 0.25),
                      'save': self.params.get('save', False), "inference_size": self.params.get('inference_size', 640),
                      "device": self.params.get('device', 'cpu')}

        for i in range(self.num_detection_threads):
            # Используем model_name как имя модели RF-DETR
            model_path = self.model_name
            
            logger_name = f"det{i}"
            thread = DetectionThreadRfdetr(model_path, self.stride, self.classes, self.source_ids, self.roi, inf_params,
                                         self.queue_out, logger_name=logger_name, parent_logger=self.logger)
            thread.start()
            self.detection_threads.append(thread)
        return True

    def reset_impl(self):
        super().reset_impl()

    def set_params_impl(self):
        super().set_params_impl()
        self.model_name = self.params.get('model', self.model_name)

    def get_params_impl(self):
        params = super().get_params_impl()
        params['model'] = self.model_name
        return params

    def get_debug_info(self, debug_info: dict):
        super().get_debug_info(debug_info)
        debug_info['model_name'] = self.model_name

    def default(self):
        super().default()
        self.model_name = None
        self.params.clear()

# Apply registration only if supported
if _SUPPORT_RFDETR:
    ObjectDetectorRfdetr = EvilEyeBase.register("ObjectDetectorRfdetr")(ObjectDetectorRfdetr)
else:
    _logger.info("ObjectDetectorRfdetr not registered due to environment constraints")
