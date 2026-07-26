"""S6: config validator warnings."""

from scripts.validate_config import validate


def test_warn_legacy_yolo_mp_detector():
    w = validate({"detectors": [{"type": "ObjectDetectorYoloMp"}]})
    assert any("ObjectDetectorYoloMp" in x for x in w)


def test_warn_mc_trackers_process_mode():
    w = validate({"mc_trackers": [{"execution_mode": "process", "enable": True}]})
    assert any("mc_trackers" in x and "process" in x for x in w)
