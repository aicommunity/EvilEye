from __future__ import annotations

import threading
from queue import Queue
from time import sleep
from typing import Any, Dict, List, Tuple

from ..core.base_class import EvilEyeBase
from ..core.frame import Frame


@EvilEyeBase.register("AttributeClassifier")
class AttributeClassifier(EvilEyeBase):
    """
    Лёгкий классификатор атрибутов для ROI-кропов первичных объектов.
    На первом этапе — заглушка: пропускает кадры дальше без модификации.

    Интерфейс для ProcessorFrame:
    - put(frame: Frame) -> bool
    - get() -> Frame | None
    - get_source_ids() -> List[int]
    - start()/stop()
    """

    ResultType = Frame

    def __init__(self):
        super().__init__()

        self.run_flag = False
        self.queue_in: Queue[Frame | None] = Queue(maxsize=2)
        self.queue_out: Queue[Frame] = Queue()
        self.processing_thread = threading.Thread(target=self._process_impl)

        # Конфиг
        self.source_ids: List[int] = []
        self.enabled: bool = True
        self.model_path: str | None = None
        self.attrs: List[str] = []
        self.conf_thresholds: Dict[str, float] = {}
        self.time_thresholds: Dict[str, Dict[str, int]] = {}
        self.ema_alpha: float = 0.6

        # Плейсхолдеры для модели
        self._model: Any = None

    def set_params_impl(self):
        self.source_ids = self.params.get('source_ids', [])
        self.enabled = self.params.get('enabled', True)
        self.model_path = self.params.get('model', None)
        self.attrs = self.params.get('attrs', [])
        self.conf_thresholds = self.params.get('confidence_thresholds', {})
        self.time_thresholds = self.params.get('time_thresholds', {})
        self.ema_alpha = float(self.params.get('ema_alpha', 0.6))

    def get_params_impl(self):
        params: Dict[str, Any] = dict()
        params['source_ids'] = self.source_ids
        params['enabled'] = self.enabled
        params['model'] = self.model_path
        params['attrs'] = self.attrs
        params['confidence_thresholds'] = self.conf_thresholds
        params['time_thresholds'] = self.time_thresholds
        params['ema_alpha'] = self.ema_alpha
        return params

    def default(self):
        self.params.clear()
        self.source_ids = []
        self.enabled = True
        self.model_path = None
        self.attrs = []
        self.conf_thresholds = {}
        self.time_thresholds = {}
        self.ema_alpha = 0.6

    def init_impl(self, **kwargs):
        # TODO: загрузка модели по self.model_path (когда появится)
        return True

    def release_impl(self):
        self._model = None

    def reset_impl(self):
        while not self.queue_in.empty():
            try:
                self.queue_in.get_nowait()
            except Exception:
                break
        while not self.queue_out.empty():
            try:
                self.queue_out.get_nowait()
            except Exception:
                break

    def put(self, frame: Frame):
        if not self.queue_in.full():
            self.queue_in.put(frame)
            return True
        else:
            try:
                _ = self.queue_in.get_nowait()
            except Exception:
                pass
            self.queue_in.put(frame)
            return True

    def get(self):
        if self.queue_out.empty():
            return None
        return self.queue_out.get()

    def get_source_ids(self) -> List[int]:
        return self.source_ids

    def start(self):
        self.run_flag = True
        if not self.processing_thread.is_alive():
            self.processing_thread = threading.Thread(target=self._process_impl)
            self.processing_thread.start()

    def stop(self):
        self.run_flag = False
        self.queue_in.put(None)
        if self.processing_thread.is_alive():
            self.processing_thread.join()

    def _process_impl(self):
        while self.run_flag:
            sleep(0.01)
            frame = self.queue_in.get()
            if frame is None:
                continue
            # Заглушка: передаём кадр дальше. Позже здесь будет инференс и публикация результатов.
            self.queue_out.put(frame)


