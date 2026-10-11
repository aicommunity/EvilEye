"""Opt-in parity against the pre-SPI AttributeDetector implementation."""

import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from evileye.attributes_detection.attribute_detector import AttributeDetector
from evileye.core.frame import Frame

pytestmark = pytest.mark.skipif(
    os.environ.get("EVILEYE_RUN_MODEL_PARITY") != "1",
    reason="set EVILEYE_RUN_MODEL_PARITY=1 to run model-backed parity",
)


def test_attribute_detector_matches_legacy_thread_golden():
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
    module = AttributeDetector()
    try:
        state = module.create_state(
            {
                "model": str(model),
                "attrs": ["person", "bottle"],
                "conf": 0.1,
                "inference_size": 224,
                "device": "cpu",
                "roi": [[]],
            }
        )
        result, output_frame = module.process_item(frame, state)

        # Captured from the legacy AttributeDetectionThread at b48c376.
        # Attribute labels are a new field in the SPI result; detections and
        # all coordinates/confidences retain the legacy values.
        assert module.get_model_class_mapping() == {"person": 0, "bottle": 39}
        assert output_frame is frame
        assert (result.source_id, result.frame_id, result.time_stamp) == (0, 17, 12.5)
        assert [item.class_id for item in result.detections] == [0, 0, 0, 0]
        assert [item.bounding_box for item in result.detections] == [
            [52, 400, 224, 893],
            [222, 398, 352, 858],
            [677, 445, 810, 877],
            [10, 463, 63, 693],
        ]
        np.testing.assert_allclose(
            [item.confidence for item in result.detections],
            [0.7693166732788086, 0.6487171649932861, 0.6340784430503845,
             0.10803212225437164],
            rtol=1e-5,
            atol=1e-6,
        )
        assert [item.detection_data["attribute"] for item in result.detections] == [
            "person", "person", "person", "person",
        ]
    finally:
        module.close()
