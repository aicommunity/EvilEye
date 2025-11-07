import time
from datetime import datetime, timedelta

from evileye.events_detectors.zone_events_detector import ZoneEventsDetector
from evileye.events_detectors.zone import Zone


class DummyTrack:
    def __init__(self, box):
        self.bounding_box = box  # [x1, y1, x2, y2]


class DummyImage:
    def __init__(self, w=1000, h=1000):
        import numpy as np
        self.image = np.zeros((h, w, 3), dtype=np.uint8)


class DummyHistObj:
    def __init__(self, source_id, object_id, frame_id, ts, box):
        self.source_id = source_id
        self.object_id = object_id
        self.frame_id = frame_id
        self.time_stamp = ts
        self.track = DummyTrack(box)
        self.last_image = DummyImage()


class DummyObj:
    def __init__(self, source_id, object_id, history):
        self.source_id = source_id
        self.object_id = object_id
        self.history = history
        self.last_image = history[-1].last_image


class DummyList:
    def __init__(self, objects):
        self.objects = objects


class DummyObjectsHandler:
    def __init__(self, active):
        self._active = active
        self._lost = DummyList([])

    def get(self, kind, source_id):
        if kind == 'active':
            return self._active
        return self._lost


def make_history_inside_zone(src_id=2, obj_id=1, start_ts=None, seconds=2, w=1000, h=1000):
    if start_ts is None:
        start_ts = datetime.now()
    hist = []
    # bottom-center point will be (500, 800) for example
    box = [450, 700, 550, 800]
    for i in range(seconds + 1):
        ts = start_ts + timedelta(seconds=i)
        hist.append(DummyHistObj(src_id, obj_id, i, ts, box))
    return hist


def test_zone_event_generated_after_threshold():
    # Zone polygon covering bottom center area in normalized coords
    zone_coords = [
        (0.3, 0.6),
        (0.7, 0.6),
        (0.7, 0.9),
        (0.3, 0.9),
    ]
    zone = Zone(2, zone_coords, 'poly', is_active=True)

    # History stays inside zone for >= 1 second
    history = make_history_inside_zone(src_id=2, obj_id=1, seconds=2)
    obj = DummyObj(2, 1, history)
    active_list = DummyList([obj])
    handler = DummyObjectsHandler(active_list)

    det = ZoneEventsDetector(handler)
    det.set_params(sources={'2': [zone_coords]}, event_threshold=1, zone_left_threshold=1)
    det.init()
    det.start()

    try:
        # Trigger update cycle
        det.update()
        time.sleep(0.05)
        events_batches = det.get()
        # events_batches is list of events; could be empty list if none
        # Detector enqueues list; normalize to flat list
        events = events_batches if isinstance(events_batches, list) else []
        assert events, "Zone events should be generated after threshold"
    finally:
        det.stop()


def test_zone_no_event_if_below_threshold():
    zone_coords = [
        (0.3, 0.6),
        (0.7, 0.6),
        (0.7, 0.9),
        (0.3, 0.9),
    ]
    history = make_history_inside_zone(seconds=0)  # 0 seconds duration
    obj = DummyObj(2, 1, history)
    active_list = DummyList([obj])
    handler = DummyObjectsHandler(active_list)

    det = ZoneEventsDetector(handler)
    det.set_params(sources={'2': [zone_coords]}, event_threshold=1, zone_left_threshold=1)
    det.init()
    det.start()
    try:
        det.update()
        time.sleep(0.05)
        events = det.get()
        assert not events, "No events expected below threshold"
    finally:
        det.stop()
