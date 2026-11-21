import copy
from datetime import datetime, timedelta
from types import SimpleNamespace as S

import numpy as np
import pytest

from evileye.events_detectors.zone_events_detector import ZoneEventsDetector
from evileye.events_detectors.event_zone import _copy_frame_image
from evileye.events_control.events_controller import EventsDetectorsController

ZONE = [[.2, .2], [.8, .2], [.8, .9], [.2, .9]]
BASE = datetime(2026, 10, 31, 12)


class Handler:
    def __init__(self):
        self.active = {}
        self.lost = {}

    def get(self, kind, source_id):
        return S(objects=getattr(self, kind).get(source_id, []))


def obj(sequence, source=0, offset=0):
    history = [S(frame_id=i+offset, object_id=1, source_id=source,
                 time_stamp=BASE+timedelta(seconds=i+offset),
                 track=S(bounding_box=[40, 20, 60, 50] if inside else [95, 20, 115, 50]))
               for i, inside in enumerate(sequence)]
    return S(source_id=source, object_id=1, history=history, track=history[-1].track,
             frame_id=history[-1].frame_id, time_stamp=history[-1].time_stamp,
             last_image=S(image=np.zeros((100, 120, 3), dtype=np.uint8)),
             time_lost=history[-1].time_stamp+timedelta(seconds=1))


@pytest.fixture
def detector():
    handler = Handler()
    det = ZoneEventsDetector(handler, listen_for_ui_events=False)
    det.set_params(sources={'0': [ZONE], '1': [ZONE]}, event_threshold=1, zone_left_threshold=1)
    det.init()
    yield det, handler
    det.release()


def test_accumulated_history_replays_complete_and_repeated_visits(detector):
    det, handler = detector
    handler.active[0] = [obj([True]*3+[False]*7+[True]*3+[False]*4)]
    events = det._process_once()
    assert [e.finished for e in events] == [False, True, False, True]
    assert [e.timestamp for e in events] == [BASE+timedelta(seconds=i) for i in (0, 3, 10, 13)]
    assert det._process_once() == []


def test_short_exit_and_incomplete_dwell(detector):
    det, handler = detector
    handler.active[0] = [obj([True, False, True, True, False, True])]
    events = det._process_once()
    assert len(events) == 1
    assert events[0].time_entered == BASE+timedelta(seconds=2)


def test_overlapping_and_reordered_history_and_lost_are_idempotent(detector):
    det, handler = detector
    current = obj([True]*3)
    current.history.reverse()
    handler.active[0] = [current]
    assert len(det._process_once()) == 1
    current.last_image = None
    handler.active[0] = []
    handler.lost[0] = [current]
    events = det._process_once()
    assert len(events) == 1 and events[0].finished
    assert events[0].img_left.image.shape == (100, 120, 3)
    assert det._process_once() == []


@pytest.mark.parametrize('replace', [False, True])
def test_zone_changes_finish_open_events_and_duplicate_delete_is_safe(detector, replace):
    det, handler = detector
    handler.active[0] = [obj([True]*3)]
    det._process_once()
    if replace:
        det.replace_zones_for_source(0, [])
    else:
        det.delete_zone(0, ZONE)
        det.delete_zone(0, ZONE)
    events = det._process_once()
    assert len(events) == 1 and events[0].finished
    assert not det.obj_ids_zone


def test_source_ids_isolate_matching_object_ids(detector):
    det, handler = detector
    handler.active = {source: [obj([True]*3, source)] for source in (0, 1)}
    assert {e.source_id for e in det._process_once()} == {0, 1}


def test_jpeg_copy_deepcopy_sticky_and_controller_publication(detector):
    det, handler = detector
    frame = _copy_frame_image(S(image=np.zeros((100, 120, 3), dtype=np.uint8)))
    for copied in (copy.copy(frame), copy.deepcopy(frame), _copy_frame_image(frame)):
        assert copied.image.shape == (100, 120, 3)
    handler.active[0] = [obj([True]*3)]
    events = det._process_once()
    controller = EventsDetectorsController([])
    controller.events_detectors = {'ZoneEventsDetector': events}
    controller._publish_events_snapshot()
    assert controller.get()['ZoneEventsDetector'][0].img_entered.image.shape == (100, 120, 3)


def test_processor_pairs_multiple_visits_in_one_batch(detector):
    from evileye.events_control.events_processor import EventsProcessor
    det, handler = detector
    handler.active[0] = [obj([True]*3+[False]*7+[True]*3+[False]*4)]
    events = det._process_once()
    processor = EventsProcessor([], None)
    processor.init()
    writes = []
    processor._adapter_call = lambda event, method, target=None: writes.append(
        (method, event.event_id, event.timestamp))
    for event in events:
        processor._process_event('ZoneEvent', event)
    assert [method for method, _, _ in writes] == ['insert', 'update', 'insert', 'update']
    assert [event_id for _, event_id, _ in writes] == [0, 0, 1, 1]
    assert processor.long_term_events['ZoneEvent'] == []
