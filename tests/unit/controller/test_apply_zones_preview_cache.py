"""apply_zones control command refreshes live preview zone overlay cache."""

from evileye.controller.controller import Controller


class _FakeDetector:
    def __init__(self):
        self.sources_list = {}

    def replace_zones_for_source(self, source_id, zones):
        self.sources_list[str(source_id)] = zones


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


def test_apply_zones_unknown_command():
    ctrl = Controller.__new__(Controller)
    assert ctrl._handle_control_command({"cmd": "other"}) == {"ok": False, "error": "unknown_command"}
