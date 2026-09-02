from types import SimpleNamespace
from unittest.mock import MagicMock

from evileye.objects_handler.object_result import ObjectResult, ObjectResultList
from evileye.objects_handler.objects_handler import ObjectsHandler


def _make_handler():
    handler = ObjectsHandler(db_controller=None, db_adapter=None)
    handler.labeling_manager = MagicMock()
    handler.save_object_images = False
    handler.save_labeling_data = False
    handler.lost_thresh = 1
    return handler


def _make_active_obj(source_id=0, track_id=7, object_id=42):
    obj = ObjectResult()
    obj.source_id = source_id
    obj.object_id = object_id
    obj.frame_id = 10
    obj.last_update = False
    obj.lost_frames = 1
    obj.track = SimpleNamespace(
        track_id=track_id,
        bounding_box=[0.1, 0.2, 0.3, 0.4],
        confidence=0.9,
    )
    obj.last_image = SimpleNamespace(width=1920, height=1080, image=None)
    return obj


def test_finalize_lost_object_continues_when_db_update_raises():
    handler = _make_handler()
    handler.db_adapter = MagicMock()
    handler.db_adapter.update.side_effect = RuntimeError("db down")
    active = _make_active_obj()
    handler.active_objs.objects = [active]

    tracking = SimpleNamespace(source_id=0, time_stamp=None)
    handler._finalize_lost_object(active, tracking)

    assert active in handler.lost_objs.objects
    assert active.last_image is None


def test_new_object_added_when_db_insert_raises():
    handler = _make_handler()
    handler.lost_thresh = 5
    handler.db_adapter = MagicMock()
    handler.db_adapter.insert.side_effect = RuntimeError("db down")
    handler._use_object_pool = False

    track = SimpleNamespace(
        track_id=3,
        class_id=0,
        bounding_box=[0.1, 0.2, 0.3, 0.4],
        confidence=0.8,
        tracking_data={},
    )
    tracking = SimpleNamespace(
        source_id=0,
        frame_id=5,
        time_stamp=None,
        tracks=[track],
    )
    image = SimpleNamespace(
        source_id=0,
        frame_id=5,
        current_video_position=0,
        image=None,
        width=1920,
        height=1080,
    )

    handler._handle_active(tracking, image)
    assert len(handler.active_objs.objects) == 1
    assert handler.active_objs.objects[0].track.track_id == 3
