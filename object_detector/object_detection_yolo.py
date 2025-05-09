import object_detector
from object_detector.detection_thread_yolo import DetectionThreadYolo


class ObjectDetectorYolo(object_detector.ObjectDetectorBase):
    id_cnt = 0  # Переменная для присвоения каждому детектору своего идентификатора

    def __init__(self):
        super().__init__()
        self.model_name = None

    def init_impl(self):
        self.detection_threads = []
        inf_params = {"show": self.params.get('show', False), 'conf': self.params.get('conf', 0.25),
                      'save': self.params.get('save', False), "imgsz": self.params.get('inference_size', 640),
                      "device": self.params.get('device', None)}

        for i in range(self.num_detection_threads):
            thread = DetectionThreadYolo(self.model_name, self.stride, self.classes, self.source_ids, self.roi, inf_params,
                                         self.queue_out)
            thread.start()
            self.detection_threads.append(thread)
        return True

    def reset_impl(self):
        super().reset_impl()

    def set_params_impl(self):
        super().set_params_impl()
        self.model_name = self.params['model']

    def get_debug_info(self, debug_info: dict):
        super().get_debug_info(debug_info)
        debug_info['model_name'] = self.model_name

    def default(self):
        super().default()
        self.model_name = None
        self.params.clear()
