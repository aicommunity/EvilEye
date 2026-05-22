import threading

import numpy as np

from evileye.core.frame_transport import SharedFrameTransport
from evileye.object_detector.mp_worker_yolo import MpWorkerYolo


class _BoxesArray:
    def __init__(self):
        self.xyxy = np.array([[1.0, 2.0, 3.0, 4.0]], dtype=np.float32)
        self.conf = np.array([0.9], dtype=np.float32)
        self.cls = np.array([2.0], dtype=np.float32)


class _Boxes:
    def cpu(self):
        return self

    def numpy(self):
        return _BoxesArray()


class _Result:
    def __init__(self):
        self.boxes = _Boxes()


class _Model:
    def predict(self, data, classes=None, verbose=False, **kwargs):
        return [_Result() for _ in data]


def test_mp_worker_yolo_returns_lightweight_payload():
    worker = MpWorkerYolo(input_queue=None, output_queue=None, stop_event=threading.Event())
    worker.model = _Model()
    worker.classes = [0, 1, 2]
    worker.inf_params = {}

    payload = worker.worker_impl([np.zeros((10, 10, 3), dtype=np.uint8)])
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert isinstance(payload[0], list)
    assert payload[0][0]["class_id"] == 2
    assert payload[0][0]["bbox_xyxy"] == [1.0, 2.0, 3.0, 4.0]


class _CudaLikeBoxes(_Boxes):
    def __init__(self):
        self._on_cpu = False

    def cpu(self):
        self._on_cpu = True
        return self

    def numpy(self):
        if not self._on_cpu:
            raise TypeError("can't convert cuda tensor to numpy")
        return _BoxesArray()


class _CudaLikeResult:
    def __init__(self):
        self.boxes = _CudaLikeBoxes()


class _CudaLikeModel:
    def predict(self, data, classes=None, verbose=False, **kwargs):
        return [_CudaLikeResult() for _ in data]


def test_mp_worker_yolo_handles_cuda_like_boxes_conversion():
    worker = MpWorkerYolo(input_queue=None, output_queue=None, stop_event=threading.Event())
    worker.model = _CudaLikeModel()
    worker.classes = [0, 1, 2]
    worker.inf_params = {}

    payload = worker.worker_impl([np.zeros((10, 10, 3), dtype=np.uint8)])
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0][0]["class_id"] == 2


def test_mp_worker_yolo_materializes_frame_handle_input():
    worker = MpWorkerYolo(input_queue=None, output_queue=None, stop_event=threading.Event())
    worker.model = _Model()
    worker.classes = [0, 1, 2]
    worker.inf_params = {}

    transport = SharedFrameTransport()
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    handle = transport.alloc_frame(frame, frame_id=1, timestamp=0.0)
    try:
        payload = worker.worker_impl([handle])
    finally:
        transport.release_frame(handle)

    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0][0]["class_id"] == 2
