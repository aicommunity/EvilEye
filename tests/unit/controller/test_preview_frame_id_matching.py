from types import SimpleNamespace

from evileye.controller.controller_processing_mixin import ControllerProcessingMixin
from evileye.core.frame import Frame
from evileye.objects_handler.object_result import ObjectResult, ObjectResultList


class _PreviewHost(ControllerProcessingMixin):
    def __init__(self, *, vis_cfg=None):
        self.source_video_duration = {}
        self.source_id_name_table = {}
        self.debug_info = {}
        self.class_mapping = {}
        self._preview_zones_by_source = {}
        self._vis_cfg = vis_cfg or {}

    def _get_preview_event_entries(self, _source_id):
        return []

    def _get_preview_event_cfg(self):
        return {}

    def _get_preview_visualizer_cfg(self):
        return dict(self._vis_cfg)


def _make_obj(source_id=0, frame_id=100):
    obj = ObjectResult()
    obj.source_id = source_id
    obj.frame_id = frame_id
    obj_list = ObjectResultList()
    obj_list.objects = [obj]
    return obj, obj_list


def test_preview_matches_objects_within_track_frame_match_window():
    host = _PreviewHost(vis_cfg={"track_frame_match_window": 10})
    frame = Frame()
    frame.source_id = 0
    frame.frame_id = 105

    obj, obj_list = _make_obj(frame_id=100)
    ctx = host._build_preview_render_context(frame, {0: obj_list})
    assert ctx.track_info == [obj]


def test_preview_fallback_active_objects_when_frame_id_far():
    host = _PreviewHost(vis_cfg={"track_frame_match_window": 1})
    frame = Frame()
    frame.source_id = 0
    frame.frame_id = 200

    obj, obj_list = _make_obj(frame_id=100)
    ctx = host._build_preview_render_context(frame, {0: obj_list})
    assert ctx.track_info == [obj]


def test_pick_preview_frame_prefers_nearest_object_frame_id():
    host = _PreviewHost()
    obj, obj_list = _make_obj(frame_id=100)

    near = Frame()
    near.source_id = 0
    near.frame_id = 102
    near.image = object()

    far = Frame()
    far.source_id = 0
    far.frame_id = 500
    far.image = object()

    picked = host._pick_preview_frame_for_source([far, near], 0, obj_list)
    assert picked is near


def test_resolve_preview_track_info_empty_without_objects():
    host = _PreviewHost()
    assert host._resolve_preview_track_info(ObjectResultList(), 10) == []
