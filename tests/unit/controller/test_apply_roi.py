"""apply_roi control command tests."""

from evileye.controller.controller import Controller


class _FakeDetector:
    def __init__(self):
        self.source_ids = [0, 2]
        self.applied = []

    def get_source_ids(self):
        return self.source_ids

    def set_rois_for_source(self, source_id, rois_xyxy):
        self.applied.append((source_id, rois_xyxy))


class _FakePipeline:
    def __init__(self, detectors):
        self._detectors = detectors

    def get_detectors(self):
        return self._detectors


def test_control_apply_roi_updates_detector_and_params():
    ctrl = Controller.__new__(Controller)
    det = _FakeDetector()
    ctrl.pipeline = _FakePipeline([det])
    ctrl.params = {
        "pipeline": {
            "detectors": [{"source_ids": [0, 2], "roi": [[], []]}],
        }
    }
    ctrl._publish_runtime_snapshot = lambda **kwargs: None

    result = ctrl._handle_control_command(
        {
            "cmd": "apply_roi",
            "source_id": 2,
            "rois": [[500, 0, 400, 300]],
        }
    )

    assert result == {"ok": True, "source_id": 2, "roi_count": 1}
    assert det.applied == [(2, [[500, 0, 899, 299]])]
    stored = ctrl.params["pipeline"]["detectors"][0]["roi"][1]
    assert stored == [[500.0, 0.0, 400.0, 300.0]]


def test_control_apply_roi_unknown_detector():
    ctrl = Controller.__new__(Controller)
    ctrl.pipeline = _FakePipeline([])
    ctrl.params = {}
    result = ctrl._handle_control_command({"cmd": "apply_roi", "source_id": 0, "rois": []})
    assert result == {"ok": False, "error": "detector_unavailable"}
