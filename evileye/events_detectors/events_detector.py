from .event import Event
from threading import Thread
from queue import Queue
from abc import ABC, abstractmethod
from ..core.base_class import EvilEyeBase


class EventsDetector(EvilEyeBase):
    def __init__(self):
        super().__init__()
        self.processing_thread = Thread(target=self.process)
        self.queue_in = Queue(maxsize=2)
        self.queue_out = Queue()
        self.run_flag = False

    def put(self, data):
        self.queue_in.put(data)

    def start(self):
        self.run_flag = True
        self.processing_thread.start()

    def stop(self):
        self.run_flag = False
        self.queue_in.put(None)
        self.processing_thread.join()

    def get(self):
        if self.queue_out.empty():
            return []
        return self.queue_out.get()

    def get_name(self):
        return self.__class__.__name__

    @abstractmethod
    def process(self):
        pass

    @abstractmethod
    def update(self):
        pass
