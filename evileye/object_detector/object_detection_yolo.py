import os
from .object_detection_base import EXEC_MODE_PROCESS, ModelBasedDetectorBase, ObjectDetectorBase
from ..core.base_class import EvilEyeBase
from ..core.mp_control import parse_mp_restart_policy


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
        restart_on_exit, no_restart_exit_codes = parse_mp_restart_policy(
            self.params,
            default_restart_on_exit=True,
        )
        self.detection_threads = []
        return self._init_process_mode(
            inf_params,
            restart_on_exit=restart_on_exit,
            no_restart_exit_codes=no_restart_exit_codes,
        )

    def _init_process_mode(self, inf_params, restart_on_exit: bool, no_restart_exit_codes: set[int]):
        """Initialize YOLO inference workers in child processes."""
        from .detection_thread_yolo_mp import DetectionThreadYoloMp

        model_path = self.model_name or self._get_default_model_name()
        if not os.path.isabs(model_path):
            model_path = os.path.join(os.getcwd(), model_path)

        for i in range(self.num_detection_threads):
            thread = DetectionThreadYoloMp(
                model_path, self.stride, self.classes,
                self.source_ids, self.roi, inf_params,
                restart_on_exit,
                no_restart_exit_codes,
                self.queue_out,
                logger_name=f"det{i}",
                parent_logger=self.logger,
                on_cuda_oom_fatal=self._report_cuda_oom_disabled,
            )
            thread.start()
            self.detection_threads.append(thread)
        try:
            from evileye.core.mp_cuda_startup import get_mp_cuda_startup_health

            get_mp_cuda_startup_health().register_expected_workers(self.num_detection_threads)
        except Exception:
            pass
        self.logger.info(
            f"Detection initialized in PROCESS mode with "
            f"{self.num_detection_threads} worker(s)"
        )
        return True
