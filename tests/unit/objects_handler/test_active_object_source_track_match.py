from evileye.object_tracker.tracking_results import TrackingResult, TrackingResultList
from evileye.objects_handler.objects_handler import ObjectsHandler
from evileye.objects_handler.object_result import ObjectResult


class _FrameStub:
    source_id = 0
    frame_id = 10
    current_video_position = 0
    width = 100
    height = 100


def _tracking_list(source_id: int, frame_id: int, track_id: int) -> TrackingResultList:
    tr = TrackingResult()
    tr.track_id = track_id
    tr.bounding_box = [source_id * 100, source_id * 100, source_id * 100 + 10, source_id * 100 + 10]
    tr.confidence = 0.9
    tr.class_id = 0
    tl = TrackingResultList()
    tl.source_id = source_id
    tl.frame_id = frame_id
    tl.tracks = [tr]
    return tl


def test_active_match_requires_source_id_not_track_id_only():
    handler = ObjectsHandler(db_controller=None)
    handler.history_len = 10
    handler._use_object_pool = False

    img0 = _FrameStub()
    img0.source_id = 0
    img1 = _FrameStub()
    img1.source_id = 1

    handler._handle_active(_tracking_list(0, 10, track_id=1), img0)
    handler._handle_active(_tracking_list(1, 10, track_id=1), img1)

    by_source = {0: [], 1: []}
    for obj in handler.active_objs.objects:
        by_source.setdefault(obj.source_id, []).append(obj)

    assert len(by_source[0]) == 1
    assert len(by_source[1]) == 1
    assert by_source[0][0].track.bounding_box[0] == 0
    assert by_source[1][0].track.bounding_box[0] == 100
