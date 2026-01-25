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
        # Try to fuse Conv+BN layers (optimization, not required)
        try:
            self.model.fuse()  # Fuse Conv+BN layers
        except Exception as e:
            # Fuse may fail with mixed precision models, continue without it
            # Note: logger may not be available in multiprocessing context
            pass
        if self.inf_params.get('half', True):
            self.model.half()

    def worker_impl(self, data: list):
        # Исключить batch_size и batch_timeout_ms из параметров для ultralytics
        filtered_params = {k: v for k, v in self.inf_params.items() 
                         if k not in ('batch_size', 'batch_timeout_ms')}
        results = self.model.predict(data, classes=self.classes, verbose=False, **filtered_params)
        cpu_results = []
        for res in results:
            cpu_results.append(res.cpu())

        del results
        return cpu_results