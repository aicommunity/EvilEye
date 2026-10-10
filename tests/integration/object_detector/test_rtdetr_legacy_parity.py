"""Opt-in golden parity against the legacy RT-DETR detector."""
import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from evileye.core.frame import Frame
from evileye.core.plugins import ModuleRuntimeContext
from evileye.object_detector.object_detection_rtdetr import ObjectDetectorRtdetr

pytestmark = pytest.mark.skipif(
    os.environ.get("EVILEYE_RUN_MODEL_PARITY") != "1",
    reason="set EVILEYE_RUN_MODEL_PARITY=1 to run model-backed parity",
)


def test_rtdetr_item_runtime_matches_legacy_thread_golden():
    root = Path(__file__).resolve().parents[3]
    model = root / "models" / "rtdetr-l.pt"
    if not model.is_file():
        pytest.skip("models/rtdetr-l.pt is unavailable")
    try:
        import ultralytics
    except ImportError:
        pytest.skip("Ultralytics is unavailable")
    image_path = Path(ultralytics.__file__).resolve().parent / "assets" / "bus.jpg"
    image = cv2.imread(str(image_path))
    if image is None:
        pytest.skip("Ultralytics bus.jpg test asset is unavailable")

    frame = Frame()
    frame.source_id, frame.frame_id, frame.time_stamp = 0, 17, 12.5
    frame.image = image
    module = ObjectDetectorRtdetr()
    try:
        state = module.create_state(
            {"model": str(model), "source_ids": [0], "roi": [[]],
             "classes": [0, 5], "conf": 0.25, "inference_size": 640,
             "device": "cpu", "half": False},
            ModuleRuntimeContext("evileye/ObjectDetectorRtdetr", "thread", (0,)),
        )
        result, output_frame = module.process_item(frame, state)
        # Golden captured from pre-item-runtime b388da3^ with identical settings.
        assert output_frame is frame
        assert (result.source_id, result.frame_id, result.time_stamp) == (0, 17, 12.5)
        assert [d.class_id for d in result.detections] == [5, 0, 0, 0, 0]
        assert [d.bounding_box for d in result.detections] == [
            [13, 232, 804, 732], [669, 394, 809, 877], [50, 398, 247, 905],
            [223, 405, 346, 861], [0, 551, 77, 869],
        ]
        np.testing.assert_allclose(
            [d.confidence for d in result.detections],
            [0.9553424715995789, 0.9486551880836487, 0.9484724402427673,
             0.9257673025131226, 0.8623334169387817],
            rtol=1e-5, atol=1e-6,
        )
    finally:
        module.close()
