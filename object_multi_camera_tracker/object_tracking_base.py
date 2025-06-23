from typing import List
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
        self.detection_history: list[DetectionResult] = []  # list of DetectionResult
        self.tracking_data = dict()  # internal tracking data


class TrackingResultList:
    def __init__(self):
        self.source_id = None
        self.frame_id = None
        self.time_stamp = None
        self.tracks: list[TrackingResult] = []  # list of DetectionResult


class ObjectMultiCameraTrackingBase(core.EvilEyeBase):

    def __init__(self):
        super().__init__()

        self.run_flag = False
        self.queue_in = Queue(maxsize=2)
        self.queue_out = Queue()
        self.source_ids = []
        self.processing_thread = threading.Thread(target=self._process_impl)

    def put(self, track_info: List[TrackingResultList]):
        if not self.queue_in.full():
            self.queue_in.put(track_info)
            return True
        
        designator = '; '.join(f"{t.source_id}:{t.frame_id}" for t in track_info)
        print(f"Failed to put tracking info {designator} to ObjectTracking queue. Queue is Full.")
        return False

    def get(self):
        if self.queue_out.empty():
            return None
        return self.queue_out.get()

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
        self.processing_thread.join()
        print('Tracker stopped')

    @abstractmethod
    def _process_impl(self):
        pass
