from ..core.mp_worker import MpWorker
from ultralytics import YOLO
from ..core.frame_transport import FrameHandle, SharedFrameTransport


class MpWorkerYolo(MpWorker):
    def __init__(self, input_queue, output_queue, log_queue=None):
        super().__init__(input_queue, output_queue, log_queue=log_queue)
        self.model_name = ""
        self.model = None
        self.classes = []
        self.inf_params = dict()
        self.is_init = False
        self._frame_transport = SharedFrameTransport()

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
        model_input = self._materialize_input_data(data)
        if any(item is None for item in model_input):
            return [[] for _ in data]
        results = self.model.predict(model_input, classes=self.classes, verbose=False, **self.inf_params)
        dto_results = []
        for res in results:
            items = []
            try:
                boxes = res.boxes
                if boxes is not None:
                    coords, confs, cls_ids = self._extract_box_arrays(boxes)
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

    def _materialize_input_data(self, data: list):
        materialized = []
        for item in data:
            if isinstance(item, FrameHandle):
                try:
                    materialized.append(self._frame_transport.get_frame_view(item))
                    continue
                except Exception:
                    materialized.append(None)
                    continue
            materialized.append(item)
        return materialized

    def _extract_box_arrays(self, boxes):
        """Extract xyxy/conf/cls arrays with minimal conversions."""
        try:
            xyxy = getattr(boxes, "xyxy", None)
            conf = getattr(boxes, "conf", None)
            cls_ids = getattr(boxes, "cls", None)
            if xyxy is not None and conf is not None and cls_ids is not None:
                try:
                    if hasattr(xyxy, "cpu"):
                        xyxy = xyxy.cpu()
                    if hasattr(conf, "cpu"):
                        conf = conf.cpu()
                    if hasattr(cls_ids, "cpu"):
                        cls_ids = cls_ids.cpu()
                except Exception:
                    pass
                coords = xyxy.tolist() if hasattr(xyxy, "tolist") else list(xyxy)
                confs = conf.tolist() if hasattr(conf, "tolist") else list(conf)
                cls = cls_ids.tolist() if hasattr(cls_ids, "tolist") else list(cls_ids)
                return coords or [], confs or [], cls or []
        except Exception:
            pass

        # Backward-compatible path for older ultralytics boxes wrappers.
        try:
            arr = boxes.cpu().numpy()
        except Exception:
            arr = boxes.numpy()
        coords = arr.xyxy.tolist() if arr.xyxy is not None else []
        confs = arr.conf.tolist() if arr.conf is not None else []
        cls = arr.cls.tolist() if arr.cls is not None else []
        return coords, confs, cls

    def cleanup(self):
        if self.model is not None:
            del self.model
            self.model = None
