from abc import ABC, abstractmethod
import core
from queue import Queue
import threading
from object_detector.object_detection_base import DetectionResultList
from object_detector.object_detection_base import DetectionResult


class TrackingResult:
    def __init__(self):
        self.track_id = 0
        self.bounding_box = []
        self.confidence = 0.0
        self.life_time = 0.0
        self.frame_count = 0
        self.class_id = None
        self.detection_history: list[DetectionResult] = [] # list of DetectionResult
        self.tracking_data = dict() # internal tracking data


class TrackingResultList:
    def __init__(self):
        self.source_id = None
        self.frame_id = None
        self.time_stamp = None
        self.tracks: list[TrackingResult] = [] # list of DetectionResult


class ObjectTrackingBase(core.EvilEyeBase):

    def __init__(self):
        super().__init__()

        self.run_flag = False
        self.queue_in = Queue()
        self.queue_out = Queue()
        self.source_ids = []
        self.processing_thread = threading.Thread(target=self._process_impl)

    def put(self, det_info):
        self.queue_in.put(det_info)

    def get(self):
        return self.queue_out.get()

    def get_source_ids(self):
        return self.source_ids

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
