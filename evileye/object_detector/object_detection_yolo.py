import os
from .object_detection_base import ObjectDetectorBase, EXEC_MODE_PROCESS
from .detection_thread_yolo import DetectionThreadYolo
from ..core.base_class import EvilEyeBase


@EvilEyeBase.register("ObjectDetectorYolo")
class ObjectDetectorYolo(ObjectDetectorBase):
    id_cnt = 0

    def __init__(self):
        super().__init__()
        self.model_name = "models/yolo11n.pt"

    def init_impl(self):
        super().init_impl()
        self.detection_threads = []
        inf_params = {
            "show": self.params.get('show', False),
            'conf': self.params.get('conf', 0.25),
            'save': self.params.get('save', False),
            "imgsz": self.params.get('inference_size', 640),
            "device": self.params.get('device', None),
        }

        if self.execution_mode == EXEC_MODE_PROCESS:
            return self._init_process_mode(inf_params)
        return self._init_thread_mode(inf_params)

    def _init_thread_mode(self, inf_params):
        """Original thread-based initialization"""
        for i in range(self.num_detection_threads):
            model_path = self.model_name
            if not os.path.isabs(model_path):
                model_path = os.path.join(os.getcwd(), model_path)

            logger_name = f"det{i}"
            thread = DetectionThreadYolo(
                model_path, self.stride, self.classes,
                self.source_ids, self.roi, inf_params,
                self.queue_out, logger_name=logger_name,
                parent_logger=self.logger,
            )
            thread.start()
            self.detection_threads.append(thread)
        return True

    def _init_process_mode(self, inf_params):
        """Multiprocessing-based initialization

        Each detection "thread" is actually backed by a child process
        via MpControl.  The DetectionThreadYoloMp class already wraps
        this pattern -- we reuse it here so that the rest of the
        pipeline (queue_in / queue_out / _process_impl) stays unchanged
        """
        from .detection_thread_yolo_mp import DetectionThreadYoloMp

        model_path = self.model_name
        if not os.path.isabs(model_path):
            model_path = os.path.join(os.getcwd(), model_path)

        for _ in range(self.num_detection_threads):
            thread = DetectionThreadYoloMp(
                model_path, self.stride, self.classes,
                self.source_ids, self.roi, inf_params,
                self.queue_out,
            )
            # DetectionThreadYoloMp starts its own mp.Process in __init__
            # but we still need to call start() for the thread wrapper
            thread.start()
            self.detection_threads.append(thread)
        self.logger.info(
            f"Detection initialized in PROCESS mode with "
            f"{self.num_detection_threads} worker(s)"
        )
        return True

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
        debug_info['execution_mode'] = self.execution_mode

    def default(self):
        super().default()
        self.model_name = None
        self.params.clear()
