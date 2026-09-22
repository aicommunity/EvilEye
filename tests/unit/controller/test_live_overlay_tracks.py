from evileye.controller.controller_processing_mixin import ControllerProcessingMixin
from evileye.core.frame import Frame
from evileye.objects_handler.object_result import ObjectResult, ObjectResultList


class _PreviewHost(ControllerProcessingMixin):
    def __init__(self, *, vis_cfg=None):
        self.source_video_duration = {}
        self.source_id_name_table = {}
        self.debug_info = {}
        self.class_mapping = {}
        self.params = {}
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


def test_live_overlay_includes_active_when_frame_id_far():
    host = _PreviewHost()
    frame = Frame()
    frame.source_id = 0
    frame.frame_id = 200

    obj, obj_list = _make_obj(frame_id=100)
    ctx = host._build_preview_render_context(frame, {0: obj_list})
    assert ctx.track_info == [obj]


def test_live_overlay_excludes_lost_countdown():
    host = _PreviewHost()
    frame = Frame()
    frame.source_id = 0
    frame.frame_id = 200

    obj, obj_list = _make_obj(frame_id=100)
    obj.lost_frames = 3
    ctx = host._build_preview_render_context(frame, {0: obj_list})
    assert ctx.track_info == []


def test_live_overlay_filters_other_source():
    host = _PreviewHost()
    frame = Frame()
    frame.source_id = 0
    frame.frame_id = 50

    other, other_list = _make_obj(source_id=1, frame_id=50)
    ctx = host._build_preview_render_context(frame, {0: other_list})
    assert ctx.track_info == []
    assert other not in ctx.track_info


def test_live_overlay_empty_without_objects():
    host = _PreviewHost()
    assert host._resolve_live_overlay_tracks(ObjectResultList(), 0) == []
    assert host._resolve_live_overlay_tracks(None, 0) == []


def test_pick_preview_frame_prefers_nearest_object_frame_id():
    host = _PreviewHost()
    _obj, obj_list = _make_obj(frame_id=100)

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
