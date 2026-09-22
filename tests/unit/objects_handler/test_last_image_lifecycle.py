from types import SimpleNamespace
from unittest.mock import MagicMock

from evileye.objects_handler.object_result import ObjectResult
from evileye.objects_handler.objects_handler import ObjectsHandler


def _make_handler():
    handler = ObjectsHandler(db_controller=None, db_adapter=None)
    handler.labeling_manager = MagicMock()
    handler.save_object_images = False
    handler.save_labeling_data = False
    handler.lost_thresh = 5
    handler._use_object_pool = False
    handler.history_len = 3
    return handler


def _track(track_id=3):
    return SimpleNamespace(
        track_id=track_id,
        class_id=0,
        bounding_box=[10, 20, 30, 40],
        confidence=0.8,
        tracking_data={},
    )


def _tracking(tracks, source_id=0, frame_id=5):
    return SimpleNamespace(
        source_id=source_id,
        frame_id=frame_id,
        time_stamp=None,
        tracks=tracks,
    )


def _image(frame_id=5):
    return SimpleNamespace(
        source_id=0,
        frame_id=frame_id,
        current_video_position=0,
        image=object(),
        width=1920,
        height=1080,
        pts_ns=None,
        media_pts_sec=None,
    )


def test_new_and_update_keep_last_image_until_lost():
    handler = _make_handler()
    frame1 = _image(frame_id=1)
    handler._handle_active(_tracking([_track(3)], frame_id=1), frame1)

    assert len(handler.active_objs.objects) == 1
    obj = handler.active_objs.objects[0]
    assert obj.last_image is frame1
    assert getattr(obj.history[-1], "last_image", None) is None

    frame2 = _image(frame_id=2)
    handler._handle_active(_tracking([_track(3)], frame_id=2), frame2)
    assert obj.last_image is frame2
    assert all(getattr(h, "last_image", None) is None for h in obj.history)

    handler._finalize_lost_object(obj, _tracking([], frame_id=3))
    assert obj.last_image is None
    assert obj in handler.lost_objs.objects
    stats = handler.get_runtime_stats()
    assert stats["lost_with_last_image"] == 0


def test_subscriber_sees_last_image_after_handle_active():
    handler = _make_handler()
    seen = {"last_image": None}

    class Spy:
        def update(self):
            active = handler.active_objs.objects
            seen["last_image"] = active[0].last_image if active else None

    handler.subscribers = [Spy()]
    frame = _image(frame_id=7)
    handler._handle_active(_tracking([_track(9)], frame_id=7), frame)
    for subscriber in handler.subscribers:
        subscriber.update()

    assert seen["last_image"] is frame
