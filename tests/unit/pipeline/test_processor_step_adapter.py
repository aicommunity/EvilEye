from evileye.core.processor_step import ProcessorStep
from evileye.core.frame import Frame


class _Proc:
    def __init__(self, requires_materialized_frame=True):
        self.requires_materialized_frame = requires_materialized_frame


def test_adapter_keeps_standard_payload_when_image_exists():
    step = ProcessorStep.__new__(ProcessorStep)
    frame = Frame()
    frame.image = "img"
    data = {"x": 1}
    proc = _Proc(requires_materialized_frame=True)
    adapted = step._adapt_input_for_processor([data, frame], proc)
    assert adapted[0] == data
    assert adapted[1] is frame
    assert adapted[1].image == "img"


def test_adapter_skips_materialization_when_not_required():
    step = ProcessorStep.__new__(ProcessorStep)
    frame = Frame()
    frame.frame_handle = object()
    data = {"x": 1}
    proc = _Proc(requires_materialized_frame=False)
    adapted = step._adapt_input_for_processor([data, frame], proc)
    assert adapted[0] == data
    assert adapted[1] is frame


def test_adapter_keeps_plain_frame_payload():
    step = ProcessorStep.__new__(ProcessorStep)
    frame = Frame()
    frame.image = "img"
    proc = _Proc(requires_materialized_frame=True)
    adapted = step._adapt_input_for_processor(frame, proc)
    assert adapted is frame
