from evileye.preprocessing.preprocessing_base import PreprocessingBase
from evileye.core.frame import Frame


class _DummyPreprocessing(PreprocessingBase):
    def init_impl(self):
        return True

    def release_impl(self):
        return None

    def reset_impl(self):
        return None

    def default(self):
        return None

    def _process_image(self, image):
        image.current_video_position = 123
        return image


def test_preprocessing_accepts_tuple_payload_and_preserves_payload():
    proc = _DummyPreprocessing()
    frame = Frame()
    frame.source_id = 1
    frame.frame_id = 2
    frame.image = "img"
    payload = {"k": "v"}

    # queue contract
    assert proc.put([payload, frame]) is True

    # descriptor/standard compatibility metadata
    assert proc.accepts_frame_handle is True
    assert proc.requires_materialized_frame is False
    assert proc.emits_dto_type == "Frame"

    # processing contract (single item)
    processed = proc._process_image(proc._materialize_frame_if_needed(frame))
    processed = proc._materialize_frame_if_needed(processed)
    from evileye.core.ipc_contracts import attach_frame_contract
    processed = attach_frame_contract(processed, payload_version=1)
    assert processed.current_video_position == 123
    assert getattr(processed, "payload_version", None) == 1
