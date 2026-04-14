from ..core.mp_worker import MpWorker
from ultralytics import YOLO


class MpWorkerYolo(MpWorker):
    def __init__(self, input_queue, output_queue, log_queue=None):
        super().__init__(input_queue, output_queue, log_queue=log_queue)
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
            self.model.fuse()
        except Exception:
            pass
        if self.inf_params.get('half', True):
            self.model.half()

    def worker_impl(self, data: list):
        results = self.model.predict(data, classes=self.classes, verbose=False, **self.inf_params)
        dto_results = []
        for res in results:
            items = []
            try:
                boxes = res.boxes
                if boxes is not None:
                    try:
                        arr = boxes.cpu().numpy()
                    except Exception:
                        arr = boxes.numpy()
                    coords = arr.xyxy.tolist() if arr.xyxy is not None else []
                    confs = arr.conf.tolist() if arr.conf is not None else []
                    cls_ids = arr.cls.tolist() if arr.cls is not None else []
                    for bbox, conf, cls_id in zip(coords, confs, cls_ids):
                        items.append(
                            {
                                "bbox_xyxy": [float(x) for x in bbox],
                                "confidence": float(conf),
                                "class_id": int(cls_id),
                            }
                        )
            except Exception:
                # Keep processing robust; malformed model output for one ROI
                # should not crash the whole detector worker.
                items = []
            dto_results.append(items)
        del results
        return dto_results

    def cleanup(self):
        if self.model is not None:
            del self.model
            self.model = None
