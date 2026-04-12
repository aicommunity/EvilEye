import os
from .object_detection_base import EXEC_MODE_PROCESS, ModelBasedDetectorBase, ObjectDetectorBase
from ..core.base_class import EvilEyeBase


@EvilEyeBase.register("ObjectDetectorYolo")
class ObjectDetectorYolo(ModelBasedDetectorBase):
    """YOLO-based object detector."""

    def __init__(self):
        super().__init__()
        self.model_name = "models/yolo11n.pt"

    def _get_detection_thread_type(self) -> str:
        return "yolo"

    def _get_default_model_name(self) -> str:
        return "models/yolo11n.pt"

    def init_impl(self):
        if self.execution_mode != EXEC_MODE_PROCESS:
            return super().init_impl()

        # Process-mode YOLO still needs the detector dispatcher thread from
        # ObjectDetectorBase: it drains detector.queue_in and forwards frames
        # into the per-worker DetectionThreadYoloMp instances.
        ObjectDetectorBase.init_impl(self)

        inf_params = {
            "show": self.params.get('show', False),
            'conf': self.params.get('conf', 0.25),
            'save': self.params.get('save', False),
            "imgsz": self.params.get('inference_size', 640),
            "device": self.params.get('device', None),
        }
        self.detection_threads = []
        return self._init_process_mode(inf_params)

    def _init_process_mode(self, inf_params):
        """Initialize YOLO inference workers in child processes."""
        from .detection_thread_yolo_mp import DetectionThreadYoloMp

        model_path = self.model_name or self._get_default_model_name()
        if not os.path.isabs(model_path):
            model_path = os.path.join(os.getcwd(), model_path)

        for i in range(self.num_detection_threads):
            thread = DetectionThreadYoloMp(
                model_path, self.stride, self.classes,
                self.source_ids, self.roi, inf_params,
                self.queue_out, logger_name=f"det{i}", parent_logger=self.logger,
            )
            thread.start()
            self.detection_threads.append(thread)
        self.logger.info(
            f"Detection initialized in PROCESS mode with "
            f"{self.num_detection_threads} worker(s)"
        )
        return True
