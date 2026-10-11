"""Opt-in parity against the pre-SPI AttributeClassifier implementation."""

import os
from pathlib import Path

import cv2
import pytest

from evileye.attributes_detection.attribute_classifier import AttributeClassifier
from evileye.core.frame import Frame
from evileye.object_tracker.tracking_results import TrackingResultList

pytestmark = pytest.mark.skipif(
    os.environ.get("EVILEYE_RUN_MODEL_PARITY") != "1",
    reason="set EVILEYE_RUN_MODEL_PARITY=1 to run model-backed parity",
)


def test_attribute_classifier_matches_legacy_roi_golden():
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
    tracking = TrackingResultList()
    tracking.source_id, tracking.frame_id = 0, 17
    tracking.roi_data = [{"track_id": 42, "roi_bbox": [52, 400, 224, 893]}]

    module = AttributeClassifier()
    try:
        state = module.create_state(
            {
                "model": str(model),
                "attrs": ["person"],
                "conf_threshold": 0.5,
                "inference_size": 224,
            }
        )
        output, output_frame = module.process_item((tracking, frame), state)

        # Captured from the pre-SPI implementation at ac1fde1.
        assert output is tracking
        assert output_frame is frame
        assert module.attr_class_mapping == {0: "person"}
        result = output.attr_results[42]["person"]
        assert result["detected_now"] is True
        assert result["class_id"] == 0
        # Ultralytics may reduce process-global CPU threads from 16 to 8
        # after other model tests. The resulting numeric drift is <0.01 px
        # and <1e-4 confidence, while pixel-scale regressions remain visible.
        assert result["bbox"] == pytest.approx(
            [0.7199851274490356, 2.678341865539551, 170.61927795410156, 493.0],
            abs=1e-2,
        )
        assert result["confidence"] == pytest.approx(
            0.8960309624671936,
            abs=1e-4,
        )
    finally:
        module.close()
