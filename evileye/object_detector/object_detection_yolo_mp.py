from .object_detection_base import ObjectDetectorBase
from .detection_thread_yolo_mp import DetectionThreadYoloMp
from ..core.base_class import EvilEyeBase


@EvilEyeBase.register("ObjectDetectorYoloMp")
class ObjectDetectorYoloMp(ObjectDetectorBase):
    id_cnt = 0  # Переменная для присвоения каждому детектору своего идентификатора

    def __init__(self):
        super().__init__()
        self.model_name = "models/yolo11n.pt"

    def init_impl(self):
        super().init_impl()
        self.detection_threads = []
        inf_params = {"show": self.params.get('show', False), 'conf': self.params.get('conf', 0.25),
                      'save': self.params.get('save', False), "imgsz": self.params.get('inference_size', 640),
                      "device": self.params.get('device', None)}

        for i in range(self.num_detection_threads):
            thread = DetectionThreadYoloMp(self.model_name, self.stride, self.classes, self.source_ids, self.roi, inf_params,
                                         self.queue_out)
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
