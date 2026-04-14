from evileye.controller.controller import Controller
from evileye.core.frame import Frame


class _DummyLogger:
    def debug(self, *args, **kwargs):
        return None


class _DummyObjHandler:
    def __init__(self):
        self.items = []

    def put(self, item):
        self.items.append(item)


def _build_controller_for_test():
    ctrl = Controller.__new__(Controller)
    ctrl.logger = _DummyLogger()
    ctrl.skip_objects_handler = False
    ctrl.obj_handler = _DummyObjHandler()
    ctrl._obj_handler_last_sent_frame_id = {}
    ctrl.source_last_processed_frame_id = {}
    ctrl._per_source_frame_debug_counter = {}
    ctrl.recording_params = None
    ctrl.event_buffers = {}
    ctrl.event_recorders = {}
    return ctrl


def test_process_pipeline_results_does_not_drop_non_empty_dict_payload():
    ctrl = _build_controller_for_test()
    frame = Frame()
    frame.source_id = 0
    frame.frame_id = 101
    payload = {
        "source_id": 0,
        "frame_id": 101,
        "tracks": [{"track_id": 1, "class_id": 0, "bbox_xyxy": [1, 2, 3, 4], "confidence": 0.9}],
    }

    frames = ctrl._process_pipeline_results([(payload, frame)])
    assert len(frames) == 1
    assert len(ctrl.obj_handler.items) == 1


def test_process_pipeline_results_throttles_empty_payload():
    ctrl = _build_controller_for_test()
    frame = Frame()
    frame.source_id = 0
    frame.frame_id = 101
    ctrl._obj_handler_last_sent_frame_id[0] = 100

    frames = ctrl._process_pipeline_results([({"tracks": []}, frame)])
    assert len(frames) == 1
    assert len(ctrl.obj_handler.items) == 0
