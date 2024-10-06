from abc import ABC, abstractmethod
import core
from queue import Queue
import threading

class DetectionResult:
    def __init__(self):
        self.bounding_box = []
        self.confidence = 0.0
        self.class_id = None
        self.detection_data = dict() # internal detection data


class DetectionResultList:
    def __init__(self):
        self.camera_id = None
        self.frame_id = None
        self.time_stamp = None
        self.detections: list[DetectionResult] = []


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

    @abstractmethod
    def _process_impl(self):
        pass
