import numpy as np

from evileye.preprocessing.preprocessing_pipeline import PreprocessingPipeline
from evileye.core.frame import Frame


def test_preprocessing_pipeline_copy_policy_and_frame_version():
    proc = PreprocessingPipeline()
    proc.params = {
        "pipeline_file_name": "",
        "in_place_allowed": False,
        "copy_required": True,
    }
    proc.set_params_impl()
    frame = Frame()
    frame.image = np.zeros((4, 4, 3), dtype=np.uint8)
    frame.frame_version = 5
    out = proc._process_image(frame)
    assert out is not frame
    assert out.frame_version == 6
