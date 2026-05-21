from types import SimpleNamespace

from evileye.controller.controller_processing_mixin import ControllerProcessingMixin
from evileye.core.frame import Frame
from evileye.objects_handler.object_result import ObjectResult, ObjectResultList


class _PreviewHost(ControllerProcessingMixin):
    def __init__(self):
        self.source_video_duration = {}
        self.source_id_name_table = {}
        self.debug_info = {}
        self.class_mapping = {}
        self._preview_zones_by_source = {}

    def _get_preview_event_entries(self, _source_id):
        return []

    def _get_preview_event_cfg(self):
        return {}

    def _get_preview_visualizer_cfg(self):
        return {}


def test_preview_does_not_use_all_objects_on_frame_mismatch():
    host = _PreviewHost()
    frame = Frame()
    frame.source_id = 0
    frame.frame_id = 105

    obj = ObjectResult()
    obj.source_id = 0
    obj.frame_id = 100
    obj_list = ObjectResultList()
    obj_list.objects = [obj]

    ctx = host._build_preview_render_context(
        frame,
        {0: obj_list},
    )
    assert ctx.track_info == []
