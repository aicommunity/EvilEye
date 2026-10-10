"""Opt-in golden parity against the legacy YOLO detector."""
import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from evileye.core.frame import Frame
from evileye.core.plugins import ModuleRuntimeContext
from evileye.object_detector.object_detection_yolo import ObjectDetectorYolo

pytestmark = pytest.mark.skipif(
    os.environ.get("EVILEYE_RUN_MODEL_PARITY") != "1",
    reason="set EVILEYE_RUN_MODEL_PARITY=1 to run model-backed parity",
)


def test_yolo_item_runtime_matches_legacy_thread_golden():
    root = Path(__file__).resolve().parents[3]
    model = root / "models" / "yolo11n.pt"
    if not model.is_file():
        pytest.skip("models/yolo11n.pt is unavailable")
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
    module = ObjectDetectorYolo()
    try:
        state = module.create_state(
            {"model": str(model), "source_ids": [0], "roi": [[]],
             "classes": [0, 5], "conf": 0.25, "inference_size": 640,
             "device": "cpu", "half": False},
            ModuleRuntimeContext("evileye/ObjectDetectorYolo", "thread", (0,)),
        )
        result, output_frame = module.process_item(frame, state)
        # Golden captured from pre-item-runtime b388da3^ with same settings.
        assert output_frame is frame
        assert (result.source_id, result.frame_id, result.time_stamp) == (0, 17, 12.5)
        assert [d.class_id for d in result.detections] == [5, 0, 0, 0, 0]
        assert [d.bounding_box for d in result.detections] == [
            [3, 229, 796, 728], [671, 394, 809, 878], [47, 399, 239, 904],
            [223, 408, 344, 860], [0, 556, 68, 872],
        ]
        np.testing.assert_allclose(
            [d.confidence for d in result.detections],
            [0.9401523470878601, 0.8882198929786682, 0.8782548308372498,
             0.8557726740837097, 0.6219192743301392],
            rtol=1e-5, atol=1e-6,
        )
    finally:
        module.close()
