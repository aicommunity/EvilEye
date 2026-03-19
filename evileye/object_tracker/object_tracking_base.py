from abc import ABC, abstractmethod
from ..core.base_class import EvilEyeBase
from queue import Queue
import threading
from .tracking_results import TrackingResultList
from queue import Full


class ObjectTrackingBase(EvilEyeBase):
    ResultType = TrackingResultList

    def __init__(self):
        super().__init__()

        self.run_flag = False
        self.queue_in = Queue(maxsize=2)
        # IMPORTANT: output queue must be bounded, otherwise results accumulate and memory grows unbounded.
        self.queue_out = Queue(maxsize=4)
        self.queue_dropped_id = Queue()
        self.source_ids = []
        self.processing_thread = None

    def put(self, det_info, force=False):
        dropped_id = []
        result = True
        if self.queue_in.full():
            if force:
                dropped_data = self.queue_in.get()
                dropped_id.append(dropped_data[1].source_id)
                dropped_id.append(dropped_data[1].frame_id)
                result = True
            else:
                dropped_id.append(det_info[1].source_id)
                dropped_id.append(det_info[1].frame_id)
                result = False
        if len(dropped_id) > 0:
            self.queue_dropped_id.put(dropped_id)

        if result:
            self.queue_in.put(det_info)

        return result

    def get(self):
        if self.queue_out.empty():
            return None
        return self.queue_out.get()

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

    def get_dropped_ids(self) -> list:
        res = []
        while not self.queue_dropped_id.empty():
            res.append(self.queue_dropped_id.get())
        return res

    def get_oueue_out_size(self):
        return self.queue_out.qsize()

    def get_source_ids(self):
        return self.source_ids

    def start(self):
        self.run_flag = True
        self.processing_thread.start()

    def stop(self):
        self.run_flag = False
        self.queue_in.put(None)
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join()
        self.logger.info('Tracker stopped')

    def init_impl(self, **kwargs):
        self.processing_thread = threading.Thread(target=self._process_impl)

    def release_impl(self):
        del self.processing_thread
        self.processing_thread = None

    @abstractmethod
    def _process_impl(self):
        pass
