import time
from datetime import datetime, timedelta

from evileye.events_detectors.zone_events_detector import ZoneEventsDetector


class DummyTrack:
    def __init__(self, box):
        self.bounding_box = box


class DummyHistObj:
    def __init__(self, source_id, object_id, frame_id, ts, box):
        self.source_id = source_id
        self.object_id = object_id
        self.frame_id = frame_id
        self.time_stamp = ts
        self.track = DummyTrack(box)


class DummyObj:
    def __init__(self, source_id, object_id, history):
        self.source_id = source_id
        self.object_id = object_id
        self.history = history
        self.last_image = None
        if history:
            self.track = DummyTrack(history[-1].track.bounding_box)
            self.time_stamp = history[-1].time_stamp


class DummyList:
    def __init__(self, objects):
        self.objects = objects


class DummyObjectsHandler:
    def __init__(self, active):
        self._active = active

    def get(self, kind, source_id):
        if kind == 'active':
            return self._active
        return DummyList([])


def _history(seconds=3):
    start = datetime.now()
    # Pixel bbox on default 1920x1080 frame; bottom-center inside normalized zone polygon.
    box = [800, 800, 1120, 1050]
    return [
        DummyHistObj(2, 1, i, start + timedelta(seconds=i), box)
        for i in range(seconds + 1)
    ]


def test_zone_detection_without_last_image_uses_default_frame_size():
    zone_coords = [[0.03, 0.10], [0.95, 0.10], [0.95, 0.99], [0.03, 0.99]]
    obj = DummyObj(2, 1, _history(seconds=3))
    handler = DummyObjectsHandler(DummyList([obj]))
    det = ZoneEventsDetector(handler)
    det.set_params(sources={'2': [zone_coords]}, event_threshold=2, zone_left_threshold=1)
    det.init()
    det.start()
    try:
        det.update()
        time.sleep(0.05)
        events = det.get()
        assert events, "Zone events should be generated without last_image"
    finally:
        det.stop()
