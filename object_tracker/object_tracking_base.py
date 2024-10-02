from abc import ABC, abstractmethod
import core
from queue import Queue
import threading


class ObjectTrackingBase(core.EvilEyeBase):

    def __init__(self):
        super().__init__()

        self.queue_in = Queue()
        self.queue_out = Queue()
        self.processing_thread = threading.Thread(target=self._process_impl, daemon=True)

    def put(self, det_info):
        self.queue_in.put(det_info)

    def get(self):
        return self.queue_out.get()

    def init_impl(self):
        self.processing_thread.start()

    @abstractmethod
    def _process_impl(self):
        pass
