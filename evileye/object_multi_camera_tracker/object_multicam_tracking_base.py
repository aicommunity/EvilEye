from typing import List, Optional, Any
from abc import ABC, abstractmethod
from ..core.base_class import EvilEyeBase
from queue import Queue, Empty
import threading
from ..object_tracker.tracking_results import TrackingResult, TrackingResultList
from queue import Full

class ObjectMultiCameraTrackingBase(EvilEyeBase):
    ResultType = TrackingResultList

    def __init__(self):
        super().__init__()

        self.run_flag = False
        self.queue_in = Queue()
        # IMPORTANT: output queue must be bounded to avoid unbounded memory growth.
        self.queue_out = Queue(maxsize=4)
        self.source_ids = []
        self.enable = False
        self.processing_thread = None

    def set_params_impl(self):
        self.source_ids = self.params.get('source_ids', [])
        self.enable = self.params.get('enable', self.enable)
        # queue_out должен быть достаточно большим, чтобы MCTracker успевал
        # эмитить весь батч (по одному элементу на камеру) без дропа "старейшего"
        # элемента. Иначе первая камера в batch может постоянно выпадать из вывода.
        # Эмит батча: len(self.source_ids) элементов.
        max_out = max(4, len(self.source_ids) * 2)
        self.queue_in = Queue(maxsize=max(2, len(self.source_ids) * 2))
        self.queue_out = Queue(maxsize=max_out)

    def get_params_impl(self):
        params = dict()
        params['enable'] = self.enable
        params['source_ids'] = self.source_ids

        return params

    def put(self, track_info: List[TrackingResultList]) -> bool:
        # Drop-oldest when input queue is full: we prefer freshest data.
        try:
            if self.queue_in.full():
                try:
                    _ = self.queue_in.get_nowait()
                except Exception:
                    pass
            self.queue_in.put_nowait(track_info)
            return True
        except Exception:
            return False

    def get(self) -> Optional[Any]:
        try:
            return self.queue_out.get_nowait()
        except Empty:
            return None

    def _put_out_drop_oldest(self, item) -> None:
        """Put to queue_out with drop-oldest behavior when full."""
        try:
            self.queue_out.put_nowait(item)
            return
        except Full:
            try:
                _ = self.queue_out.get_nowait()
            except Exception:
                pass
            try:
                self.queue_out.put_nowait(item)
            except Exception:
                pass

    def get_queue_out_size(self) -> int:
        return self.queue_out.qsize()

    def get_source_ids(self):
        return self.source_ids

    def start(self):
        self.run_flag = True
        if self.processing_thread is None or not self.processing_thread.is_alive():
            self.processing_thread = threading.Thread(target=self._process_impl)
        self.processing_thread.start()

    def stop(self):
        self.run_flag = False
        self.queue_in.put(None)
        if self.processing_thread.is_alive():
            self.processing_thread.join()
        self.logger.info('Tracker stopped')

    @abstractmethod
    def _process_impl(self):
        pass
