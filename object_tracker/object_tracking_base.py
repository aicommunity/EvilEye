from abc import ABC, abstractmethod
import core
from queue import Queue
import threading


class ObjectTrackingBase(core.EvilEyeBase):

    def __init__(self):
        super().__init__()

        self.run_flag = False
        self.queue_in = Queue()
        self.queue_out = Queue()
        self.processing_thread = threading.Thread(target=self._process_impl)

    def put(self, det_info):
        self.queue_in.put(det_info)

    def get(self):
        return self.queue_out.get()

    def start(self):
        self.run_flag = True
        self.processing_thread.start()

    def stop(self):
        self.run_flag = False
        self.queue_in.put(None)
        self.processing_thread.join()
        print('Tracker stopped')

    @abstractmethod
    def _process_impl(self):
        pass
