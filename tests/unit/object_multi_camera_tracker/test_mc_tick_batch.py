import datetime
from unittest.mock import MagicMock

from evileye.core.frame import Frame
from evileye.object_multi_camera_tracker.custom_object_tracking import (
    MC_MAX_FRAME_ID_SPREAD,
    ObjectMultiCameraTracking,
)
from evileye.object_tracker.tracking_results import TrackingResult, TrackingResultList


def _make_mc(source_ids=None) -> ObjectMultiCameraTracking:
    mc = ObjectMultiCameraTracking()
    mc.source_ids = source_ids or [0, 1, 2]
    mc.enable = False
    mc.tracker = MagicMock()
    return mc


def _pair(source_id: int, frame_id: int):
    track_info = TrackingResultList()
    track_info.source_id = source_id
    track_info.frame_id = frame_id
    tr = TrackingResult()
    tr.track_id = 1
    tr.bounding_box = [0, 0, 10, 10]
    tr.tracking_data = {"track_object": MagicMock()}
    track_info.tracks = [tr]
    frame = Frame()
    frame.source_id = source_id
    frame.frame_id = frame_id
    frame.time_stamp = datetime.datetime.now()
    return track_info, frame


def test_full_batch_emit_passthrough():
    mc = _make_mc([0, 1])
    batch = {0: _pair(0, 10), 1: _pair(1, 11)}
    out = mc.process_tick_batch(batch)
    assert len(out) == 2
    assert mc._last_emitted_frame_id_by_source[0] == 10
    assert mc._last_emitted_frame_id_by_source[1] == 11


def test_incomplete_batch_no_emit():
    mc = _make_mc([0, 1, 2])
    batch = {0: _pair(0, 1), 1: _pair(1, 2)}
    assert mc.process_tick_batch(batch) == []


def test_spread_too_large_no_emit():
    import datetime

    mc = _make_mc([0, 1])
    now = datetime.datetime.now()
    p0 = _pair(0, 0)
    p1 = _pair(1, MC_MAX_FRAME_ID_SPREAD + 10)
    p0[1].time_stamp = now
    p1[1].time_stamp = now + datetime.timedelta(seconds=8)
    batch = {0: p0, 1: p1}
    assert mc.process_tick_batch(batch) == []


def test_last_emitted_blocks_repeat():
    mc = _make_mc([0])
    batch = {0: _pair(0, 5)}
    assert len(mc.process_tick_batch(batch)) == 1
    assert mc.process_tick_batch(batch) == []


def test_ingest_tick_batch_waits_for_all_sources():
    mc = _make_mc([0, 1, 2])
    mc.enable = False
    assert mc.ingest_tick_batch({0: _pair(0, 1)}) == []
    assert len(mc.ingest_tick_batch({1: _pair(1, 2), 2: _pair(2, 3)})) == 3


def test_ingest_prunes_stale_accumulator_on_spread():
    import datetime

    mc = _make_mc([0, 1])
    mc.enable = False
    now = datetime.datetime.now()
    p0 = _pair(0, 0)
    p1 = _pair(1, 1)
    p0[1].time_stamp = now
    p1[1].time_stamp = now + datetime.timedelta(seconds=8)
    mc.ingest_tick_batch({0: p0})
    assert mc.ingest_tick_batch({1: p1}) == []
    assert 0 not in mc._accumulated_tick_batch
    assert mc._diag_tick_batch_stale_evict >= 1


def test_timestamp_spread_allows_skewed_frame_ids():
    import datetime

    mc = _make_mc([0, 1])
    mc.enable = False
    now = datetime.datetime.now()
    p0 = _pair(0, 1000)
    p1 = _pair(1, 10)
    p0[1].time_stamp = now
    p1[1].time_stamp = now + datetime.timedelta(milliseconds=200)
    out = mc.process_tick_batch({0: p0, 1: p1})
    assert len(out) == 2


def test_accumulator_rejects_stale_frame_id_regression():
    mc = _make_mc([0, 1])
    mc.enable = False
    mc.ingest_tick_batch({0: _pair(0, 100)})
    mc.ingest_tick_batch({0: _pair(0, 50)})
    assert mc._frame_id_for_pair(*mc._accumulated_tick_batch[0]) == 100


def test_processor_step_calls_tick_batch(monkeypatch):
    from evileye.core.processor_step import ProcessorStep

    mc = _make_mc([0])
    mc.ingest_tick_batch = MagicMock(return_value=[_pair(0, 1)])

    step = ProcessorStep("mc_trackers", "ObjectMultiCameraTracking", 1, 4)
    step.processors = [mc]
    track_info, frame = _pair(0, 1)
    out = step.process([ [track_info, frame] ])
    mc.ingest_tick_batch.assert_called_once()
    assert len(out) == 1
