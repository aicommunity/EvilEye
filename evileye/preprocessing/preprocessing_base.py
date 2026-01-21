from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from queue import Empty, Full, Queue
from typing import List, Optional

from ..core.base_class import EvilEyeBase
from ..core.frame import Frame


class PreprocessingBase(EvilEyeBase, ABC):
    """Базовый класс для препроцессоров кадра."""

    ResultType = Frame

    def __init__(self):
        super().__init__()

        self.run_flag = False
        self.queue_in: Queue[Optional[Frame]] = Queue(maxsize=2)
        self.queue_out: Queue[Optional[Frame]] = Queue()
        self.source_ids: List[int] = []
        self.processing_thread = threading.Thread(target=self._process_impl, daemon=True)

    def set_params_impl(self):
        self.source_ids = self.params.get("source_ids", [])

    def get_params_impl(self):
        params = dict()
        params["source_ids"] = self.source_ids
        return params

    def put(self, det_info: Frame) -> bool:
        try:
            if not self.queue_in.full():
                self.queue_in.put(det_info, timeout=0.01)
                return True
            old_info = self.queue_in.get_nowait()
            self.logger.info(
                "Preprocessing queue for %s is full. Remove oldest frame %s",
                getattr(det_info, "source_id", "unknown"),
                getattr(old_info, "frame_id", "unknown"),
            )
        except Empty:
            pass
        except Full:
            return False
        return False

    def get(self) -> Optional[Frame]:
        if self.queue_out.empty():
            return None
        return self.queue_out.get()

    def get_queue_out_size(self) -> int:
        return self.queue_out.qsize()

    def get_source_ids(self):
        return self.source_ids

    def start(self):
        self.run_flag = True
        if not self.processing_thread.is_alive():
            self.processing_thread.start()

    def stop(self):
        self.run_flag = False
        try:
            self.queue_in.put_nowait(None)
        except Full:
            pass
        if self.processing_thread.is_alive():
            self.processing_thread.join()
        self.logger.info("Preprocessing stopped")

    def _process_impl(self):
        while self.run_flag:
            try:
                image = self.queue_in.get(timeout=0.1)
            except Empty:
                continue

            if image is None:
                continue

            preprocessed_image = self._process_image(image)
            if preprocessed_image is not None:
                self.queue_out.put(preprocessed_image)

    @abstractmethod
    def _process_image(self, image: Frame) -> Optional[Frame]:
        """Реализация обработки кадра в конкретном препроцессоре."""
        raise NotImplementedError
