from __future__ import annotations

import threading
from queue import Queue
from time import sleep
from typing import Any, Dict, List, Tuple

from ..core.base_class import EvilEyeBase
from ..core.frame import Frame


@EvilEyeBase.register("RoiFeeder")
class RoiFeeder(EvilEyeBase):
    """
    Лёгкий процессор для подготовки ROI по bbox первичных объектов.
    На первом этапе реализует pass-through, сохраняя интерфейс ProcessorFrame.

    Требуемый интерфейс для ProcessorFrame:
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

        # Конфигурируемые параметры
        self.source_ids: List[int] = []
        self.padding: float = 0.0
        self.roi_size: Tuple[int, int] | None = None  # (w, h)
        self.every_n_frames: int = 1

        # Внутренняя книга учёта частоты
        self._frame_counters = {}  # Dict[int, int]

    def set_params_impl(self):
        self.source_ids = self.params.get('source_ids', [])
        self.padding = float(self.params.get('padding', 0.0))
        size = self.params.get('size', None)
        if isinstance(size, (list, tuple)) and len(size) == 2:
            self.roi_size = (int(size[0]), int(size[1]))
        self.every_n_frames = int(self.params.get('every_n_frames', 1))

    def get_params_impl(self):
        params: Dict[str, Any] = dict()
        params['source_ids'] = self.source_ids
        params['padding'] = self.padding
        params['size'] = list(self.roi_size) if self.roi_size else None
        params['every_n_frames'] = self.every_n_frames
        return params

    def default(self):
        self.params.clear()
        self.source_ids = []
        self.padding = 0.0
        self.roi_size = None
        self.every_n_frames = 1

    def init_impl(self, **kwargs):
        return True

    def release_impl(self):
        pass

    def reset_impl(self):
        # Очистка очередей
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
        self._frame_counters.clear()

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

            # Проверяем, нужно ли обрабатывать этот кадр
            if frame.source_id not in self.source_ids:
                # Передаем кадр дальше даже если source_id не подходит
                self.queue_out.put(frame)
                continue
                
            # Увеличиваем счетчик кадров для этого источника
            if frame.source_id not in self._frame_counters:
                self._frame_counters[frame.source_id] = 0
            self._frame_counters[frame.source_id] += 1
            
            # Всегда передаем кадр дальше, но обрабатываем атрибуты только для нужных кадров
            # На первом этапе — pass-through кадра далее по конвейеру
            # (позже здесь появится извлечение bbox первичных и подготовка ROI)
            self.queue_out.put(frame)


