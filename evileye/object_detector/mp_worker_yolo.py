from ..core.mp_worker import MpWorker
from ultralytics import YOLO

class MpWorkerYolo(MpWorker):
    def __init__(self, input_queue, output_queue):
        super().__init__(input_queue, output_queue)
        self.model_name = ""
        self.model = None
        self.classes = []
        self.inf_params = dict()
        self.is_init = False

    def set_params(self, model_name, classes, inf_params):
        self.model_name = model_name
        self.model = None
        self.classes = classes
        self.inf_params = inf_params
        self.is_init = True

    def init_worker(self):
        self.model = YOLO(self.model_name)
        self.model.fuse()  # Fuse Conv+BN layers
        if self.inf_params.get('half', True):
            self.model.half()

    def worker_impl(self, data: list):
        results = self.model.predict(data, classes=self.classes, verbose=False, **self.inf_params)
        cpu_results = []
        for res in results:
            cpu_results.append(res.cpu())

        del results
        return cpu_results