from typing import List, Optional, Any
from abc import ABC, abstractmethod
from ..core.base_class import EvilEyeBase
from queue import Queue, Empty
import threading
from ..object_tracker.tracking_results import TrackingResult, TrackingResultList

class ObjectMultiCameraTrackingBase(EvilEyeBase):
    ResultType = TrackingResultList

    def __init__(self):
        super().__init__()

        self.run_flag = False
        self.queue_in = Queue()
        self.queue_out = Queue()
        self.source_ids = []
        self.enable = False
        self.processing_thread = None

    def set_params_impl(self):
        self.source_ids = self.params.get('source_ids', [])
        self.enable = self.params.get('enable', self.enable)
        self.queue_in = Queue(maxsize=len(self.source_ids)*2)

    def get_params_impl(self):
        params = dict()
        params['enable'] = self.enable
        params['source_ids'] = self.source_ids

        return params

    def put(self, track_info: List[TrackingResultList]) -> bool:
        if not self.queue_in.full():
            self.queue_in.put(track_info)
            return True
        
        return False

    def get(self) -> Optional[Any]:
        try:
            return self.queue_out.get_nowait()
        except Empty:
            return None

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
