from evileye.api.core.zone_config import (
    detector_zones_for_source,
    normalize_polygon_coords,
    set_detector_zones_for_source,
    set_zone_detector_params,
    ui_zones_from_detector,
    ui_zones_to_detector,
    zone_detector_params,
)
from evileye.events_detectors.zone_events_detector import ZoneEventsDetector


def test_normalize_polygon_coords_unwraps_extra_nesting():
    nested = [[[
        [0.03, 0.10],
        [0.95, 0.10],
        [0.95, 0.99],
        [0.03, 0.99],
    ]]]
    coords = normalize_polygon_coords(nested)
    assert coords is not None
    assert len(coords) == 4
    assert coords[0] == [0.03, 0.10]


def test_detector_zones_round_trip_via_sources():
    body = {
        "events_detectors": {
            "ZoneEventsDetector": {
                "sources": {
                    "2": [
                        [
                            [0.03, 0.10],
                            [0.95, 0.10],
                            [0.95, 0.99],
                            [0.03, 0.99],
                        ]
                    ]
                }
            }
        }
    }
    zones = detector_zones_for_source(body, 2)
    assert len(zones) == 1
    ui = ui_zones_from_detector(zones)
    assert ui[0]["type"] == "polygon"
    assert len(ui[0]["points"]) == 4

    converted = ui_zones_to_detector(ui)
    set_detector_zones_for_source(body, 2, converted)
    stored = body["events_detectors"]["ZoneEventsDetector"]["sources"]["2"]
    assert stored == converted


def test_zone_detector_params_round_trip():
    body: dict = {"events_detectors": {"ZoneEventsDetector": {"event_threshold": 1}}}
    assert zone_detector_params(body) == {
        "event_threshold": 1,
        "zone_left_threshold": 3,
    }
    set_zone_detector_params(body, event_threshold=4, zone_left_threshold=5)
    assert zone_detector_params(body) == {
        "event_threshold": 4,
        "zone_left_threshold": 5,
    }


def test_apply_thresholds_updates_detector():
    class _Handler:
        def get(self, kind, source_id):
            class _List:
                objects = []
            return _List()

    det = ZoneEventsDetector(_Handler())
    det.set_params(sources={"2": []}, event_threshold=1, zone_left_threshold=2)
    det.init()
    det.apply_thresholds(event_threshold=7, zone_left_threshold=9)
    assert det.event_threshold == 7
    assert det.zone_left_threshold == 9


def test_replace_zones_for_source_resets_tracking_state():
    class _Handler:
        def get(self, kind, source_id):
            class _List:
                objects = []
            return _List()

    det = ZoneEventsDetector(_Handler())
    det.set_params(sources={"2": []}, event_threshold=1, zone_left_threshold=1)
    det.init()
    det.sources_zones[2] = []
    det.obj_ids_zone = {}
    det.left_frame_id[2] = {99: {0: 1}}
    det.entered_frame_id[2] = {99: {0: 1}}

    new_zone = [[0.03, 0.10], [0.95, 0.10], [0.95, 0.99], [0.03, 0.99]]
    det.replace_zones_for_source(2, [new_zone])

    assert det.left_frame_id[2] == {}
    assert det.entered_frame_id[2] == {}
    assert len(det.sources_zones[2]) == 1
    assert det.sources_list["2"] == [new_zone]
