from abc import ABC, abstractmethod
import core
from queue import Queue
import threading


class ObjectDetectorBase(core.EvilEyeBase):

    def __init__(self):
        super().__init__()

        self.run_flag = False
        self.queue_in = Queue()
        self.queue_out = Queue()
        self.processing_thread = threading.Thread(target=self._process_impl)

    def put(self, image):
        self.queue_in.put(image)

    def get(self):
        return self.queue_out.get()

    def start(self):
        self.run_flag = True
        self.processing_thread.start()

    def stop(self):
        self.run_flag = False
        self.queue_in.put('STOP')
        self.processing_thread.join()
        print('Detection stopped')
    # def process(self, image, all_roi=[]):
    #     if self.get_init_flag():
    #         self._process_impl()
    #     else:
    #         raise Exception('init function has not been called')

    @abstractmethod
    def _process_impl(self):
        pass
