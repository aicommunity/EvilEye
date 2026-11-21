from datetime import datetime, timedelta

from evileye.object_tracker.tracking_results import TrackingResult, TrackingResultList
from evileye.objects_handler.labeling_manager import LabelingManager
from evileye.objects_handler.object_result import ObjectResult
from evileye.objects_handler.objects_handler import ObjectsHandler


class _FrameStub:
    source_id = 0
    frame_id = 10
    current_video_position = 0
    width = 100
    height = 100
    pts_ns = 2_000_000_000
    media_pts_sec = 2.0


class _Track:
    bounding_box = [1, 2, 11, 22]
    confidence = 0.9
    track_id = 7


def _tracking_list(source_id: int, frame_id: int, track_id: int, ts) -> TrackingResultList:
    tr = TrackingResult()
    tr.track_id = track_id
    tr.bounding_box = [0, 0, 10, 10]
    tr.confidence = 0.9
    tr.class_id = 0
    tl = TrackingResultList()
    tl.source_id = source_id
    tl.frame_id = frame_id
    tl.time_stamp = ts
    tl.tracks = [tr]
    return tl


def test_time_lost_uses_last_seen_frame_not_now():
    handler = ObjectsHandler(db_controller=None)
    handler.history_len = 10
    handler.lost_thresh = 2
    handler.save_object_images = False
    handler.save_labeling_data = False
    handler._use_object_pool = False

    seen = datetime(2026, 8, 17, 10, 0, 0)
    img = _FrameStub()
    handler._handle_active(_tracking_list(0, 10, 1, seen.timestamp()), img)
    last_seen = handler.active_objs.objects[0].time_stamp
    assert last_seen == seen

    empty = TrackingResultList()
    empty.source_id = 0
    empty.frame_id = 11
    empty.time_stamp = (seen + timedelta(seconds=5)).timestamp()
    empty.tracks = []
    handler._handle_active(empty, img)
    handler._handle_active(empty, img)

    assert handler.lost_objs.objects
    lost = handler.lost_objs.objects[0]
    assert lost.time_lost == last_seen
    assert (datetime.now() - lost.time_lost).total_seconds() > 60


def test_detections_folder_uses_object_timestamp_not_today():
    handler = ObjectsHandler(db_controller=None)
    obj = ObjectResult()
    obj.time_stamp = datetime(2026, 1, 2, 23, 59, 0)
    obj.time_detected = obj.time_stamp
    obj.time_lost = datetime(2026, 1, 3, 0, 1, 0)
    assert handler._event_date_str(obj, lost=False) == "2026-01-02"
    assert handler._event_date_str(obj, lost=True) == "2026-01-03"


def test_found_json_includes_media_pts(tmp_path):
    manager = LabelingManager(base_dir=str(tmp_path), preload_data=False)
    obj = ObjectResult()
    obj.object_id = 5
    obj.frame_id = 3
    obj.source_id = 0
    obj.class_id = 0
    obj.time_stamp = datetime(2026, 8, 17, 10, 0, 0)
    obj.track = _Track()
    obj.media_pts_sec = 1.25
    obj.pts_ns = 1_250_000_000
    data = manager.create_found_object_data(obj, 1920, 1080, "frame.jpeg", "preview.jpeg")
    assert data["media_pts_sec"] == 1.25
    assert data["pts_ns"] == 1_250_000_000
    assert "2026-08-17" in data["image_filename"]
