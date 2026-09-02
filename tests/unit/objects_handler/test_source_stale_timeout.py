from types import SimpleNamespace
from unittest.mock import MagicMock

from evileye.objects_handler.object_result import ObjectResult
from evileye.objects_handler.objects_handler import ObjectsHandler


def _make_handler():
    handler = ObjectsHandler(db_controller=None, db_adapter=None)
    handler.labeling_manager = MagicMock()
    handler.save_object_images = False
    handler.save_labeling_data = False
    handler.source_stale_sec = 5.0
    handler.lost_thresh = 99
    return handler


def _make_active(source_id: int, track_id: int):
    obj = ObjectResult()
    obj.source_id = source_id
    obj.object_id = track_id
    obj.track = SimpleNamespace(track_id=track_id, bounding_box=[0, 0, 1, 1], confidence=0.5)
    obj.last_image = None
    return obj


def test_expire_stale_source_objects_moves_active_to_lost():
    handler = _make_handler()
    stale_obj = _make_active(0, 1)
    fresh_obj = _make_active(1, 2)
    handler.active_objs.objects = [stale_obj, fresh_obj]
    handler._last_frame_ts_by_source = {0: 100.0, 1: 199.0}

    handler._expire_stale_source_objects(now=200.0, exclude_source_id=1)

    assert stale_obj in handler.lost_objs.objects
    assert fresh_obj in handler.active_objs.objects
    assert stale_obj not in handler.active_objs.objects
