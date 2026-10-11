"""apply_zones control command refreshes live preview zone overlay cache."""

from evileye.controller.controller import Controller


class _FakeDetector:
    def __init__(self):
        self.config = {"sources": {}}
        self.commands = []

    def get_params(self):
        return self.config

    def submit_command(self, command, *, config_patch=None, **kwargs):
        self.commands.append((command, kwargs))
        if config_patch:
            self.config.update(config_patch)


def test_apply_zones_refreshes_preview_zones_cache():
    ctrl = Controller.__new__(Controller)
    ctrl.params = {"events_detectors": {"ZoneEventsDetector": {"sources": {}}}}
    ctrl.zone_events_detector = _FakeDetector()
    zones = [[[0.03, 0.10], [0.95, 0.10], [0.95, 0.99], [0.03, 0.99]]]
    refreshed = {2: [["poly", zones[0], None]]}

    def _extract():
        return refreshed

    ctrl._extract_preview_zones = _extract
    ctrl._preview_zones_by_source = {}
    ctrl._publish_runtime_snapshot = lambda **kwargs: None

    result = ctrl._handle_control_command(
        {"cmd": "apply_zones", "source_id": 2, "zones": zones}
    )

    assert result == {"ok": True, "source_id": 2, "zone_count": 1}
    assert ctrl._preview_zones_by_source == refreshed
    assert ctrl.zone_events_detector.commands[0][0] == "replace_zones_for_source"
    assert ctrl.params["events_detectors"]["ZoneEventsDetector"]["sources"]["2"] == zones


def test_apply_zones_unknown_command():
    ctrl = Controller.__new__(Controller)
    assert ctrl._handle_control_command({"cmd": "other"}) == {"ok": False, "error": "unknown_command"}


def test_apply_zone_detector_params_updates_runtime():
    ctrl = Controller.__new__(Controller)
    ctrl.params = {"events_detectors": {"ZoneEventsDetector": {}}}

    class _FakeDetector:
        def __init__(self):
            self.config = {"event_threshold": 1, "zone_left_threshold": 2}
            self.commands = []

        def get_params(self):
            return self.config

        def submit_command(self, command, *, config_patch=None, **kwargs):
            self.commands.append((command, kwargs))
            if config_patch:
                self.config.update(config_patch)

    ctrl.zone_events_detector = _FakeDetector()
    ctrl._publish_runtime_snapshot = lambda **kwargs: None

    result = ctrl._handle_control_command(
        {"cmd": "apply_zone_detector_params", "event_threshold": 4, "zone_left_threshold": 6}
    )

    assert result["ok"] is True
    assert result["event_threshold"] == 4
    assert result["zone_left_threshold"] == 6
    assert ctrl.params["events_detectors"]["ZoneEventsDetector"]["event_threshold"] == 4
    assert ctrl.params["events_detectors"]["ZoneEventsDetector"]["zone_left_threshold"] == 6
