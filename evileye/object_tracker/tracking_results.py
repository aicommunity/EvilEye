import copy

from ..object_detector.object_detection_base import DetectionResultList
from ..object_detector.object_detection_base import DetectionResult

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
    generator_counter = 0
    def __init__(self):
        self.source_id = None
        self.frame_id = None
        self.time_stamp = None
        self.tracks: list[TrackingResult] = []  # list of DetectionResult

    def generate_from(self, data):
        if type(data) == DetectionResultList:
            detections = data
            for detection in detections.detections:
                track = TrackingResult()
                track.track_id = TrackingResultList.generator_counter
                TrackingResultList.generator_counter += 1
                track.bounding_box = detection.bounding_box
                track.confidence = 1.0
                track.life_time = 0.0
                track.frame_count = 0
                track.class_id = detection.class_id
                self.tracks.append(track)
        elif type(data) == TrackingResultList:
            tracks = data
            self.tracks = tracks.tracks
            self.source_id = tracks.source_id
            self.frame_id = tracks.frame_id
            self.time_stamp = tracks.time_stamp
