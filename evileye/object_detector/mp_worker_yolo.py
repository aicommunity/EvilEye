import os
from pathlib import Path

from ..core.mp_worker import MpWorker
from ..core.frame_transport import SharedFrameTransport, materialize_payload_list
from .yolo_runtime import YoloRuntime


class MpWorkerYolo(MpWorker):
    def __init__(self, input_queue, output_queue, log_queue=None, stop_event=None):
        super().__init__(input_queue, output_queue, log_queue=log_queue, stop_event=stop_event)
        self.model_name = ""
        self.classes = []
        self.inf_params = dict()
        self.is_init = False
        self._frame_transport = SharedFrameTransport()
        self._yolo = YoloRuntime(
            logger=self.logger if hasattr(self, "logger") else None,
        )

    @property
    def model(self):
        return self._yolo.model

    @model.setter
    def model(self, value) -> None:
        self._yolo.model = value

    def set_params(self, model_name, classes, inf_params):
        self.model_name = model_name
        self.classes = classes
        self.inf_params = inf_params
        self.is_init = True
        self._yolo.configure(model_name, classes, inf_params)

    def get_spawn_state(self):
        return {
            "model_name": self.model_name,
            "classes": self.classes,
            "inf_params": self.inf_params,
        }

    def apply_spawn_state(self, state):
        self.set_params(
            state.get("model_name", ""),
            state.get("classes", []),
            state.get("inf_params", {}),
        )

    def init_worker(self):
        self._yolo.load()

    def worker_impl(self, data: list):
        self._yolo.classes = self.classes
        self._yolo.inf_params = self.inf_params
        model_input = self._materialize_input_data(data)
        if any(item is None for item in model_input):
            return [[] for _ in data]
        return self._yolo.predict(model_input)

    def _materialize_input_data(self, data: list):
        return materialize_payload_list(data, self._frame_transport)

    def cleanup(self):
        self._yolo.release()
