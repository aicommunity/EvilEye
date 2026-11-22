"""S6: config validator warnings."""

from scripts.validate_config import validate


def test_warn_legacy_yolo_mp_detector():
    w = validate({"detectors": [{"type": "ObjectDetectorYoloMp"}]})
    assert any("ObjectDetectorYoloMp" in x for x in w)


def test_warn_mc_trackers_process_mode():
    w = validate({"mc_trackers": [{"execution_mode": "process", "enable": True}]})
    assert any("mc_trackers" in x and "process" in x and "ignored" in x for x in w)


def test_warn_mc_trackers_thread_mode():
    w = validate({"mc_trackers": [{"execution_mode": "thread", "enable": True}]})
    assert any("execution_mode=thread" in x and "ignored" in x for x in w)


def test_mc_trackers_without_execution_mode_is_silent():
    w = validate({"mc_trackers": [{"enable": True, "stage_kind": "sync_batch"}]})
    assert not any("mc_trackers" in x for x in w)


def test_warn_disabled_mc_trackers_still_flags_execution_mode():
    w = validate({"mc_trackers": [{"execution_mode": "thread", "enable": False}]})
    assert any("execution_mode=thread" in x and "ignored" in x for x in w)


def test_disabled_mc_trackers_without_execution_mode_is_silent():
    w = validate({"mc_trackers": [{"enable": False}]})
    assert not any("mc_trackers" in x for x in w)
