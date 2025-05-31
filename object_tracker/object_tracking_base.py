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

    def generate_from(self, detections: DetectionResultList):
        for detection in detections.detections:
            track = TrackingResult()
            track.track_id = len(self.tracks)
            track.bounding_box = detection.bounding_box
            track.confidence = 1.0
            track.life_time = 0.0
            track.frame_count = 0
            track.class_id = detection.class_id
            track.detection_history.append(detection)


class ObjectTrackingBase(core.EvilEyeBase):

    def __init__(self):
        super().__init__()

        self.run_flag = False
        self.queue_in = Queue(maxsize=2)
        self.queue_out = Queue()
        self.queue_dropped_id = Queue()
        self.source_ids = []
        self.processing_thread = threading.Thread(target=self._process_impl)

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
        self.processing_thread.join()
        print('Tracker stopped')

    @abstractmethod
    def _process_impl(self):
        pass
