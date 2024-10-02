from abc import ABC, abstractmethod
import core
from queue import Queue
import threading


class ObjectDetectorBase(core.EvilEyeBase):

    def __init__(self):
        super().__init__()

        self.queue_in = Queue()
        self.queue_out = Queue()
        self.processing_thread = threading.Thread(target=self._process_impl, daemon=True)

    def put(self, image):
        self.queue_in.put(image)

    def get(self):
        return self.queue_out.get()

    def init_impl(self):
        self.processing_thread.start()
        return True

    # def process(self, image, all_roi=[]):
    #     if self.get_init_flag():
    #         self._process_impl()
    #     else:
    #         raise Exception('init function has not been called')

    @abstractmethod
    def _process_impl(self):
        pass
