"""ROI configuration helpers unit tests."""

import pytest

from evileye.api.core.roi_config import (
    detector_entry_for_source,
    detector_rois_for_source,
    set_detector_rois_for_source,
    ui_rois_from_detector,
    ui_rois_to_detector,
    xywh_list_to_xyxy_int,
)


def _sample_body() -> dict:
    return {
        "pipeline": {
            "sources": [
                {
                    "source_ids": [0, 2],
                    "source_names": ["Cam1", "Cam3"],
                    "frame_width": 1920,
                    "frame_height": 1080,
                }
            ],
            "detectors": [
                {
                    "source_ids": [0, 2],
                    "roi": [
                        [[100, 50, 200, 100]],
                        [[500, 0, 400, 300], [10, 10, 20, 20]],
                    ],
                }
            ],
        }
    }


def test_detector_entry_for_source():
    body = _sample_body()
    entry = detector_entry_for_source(body, 2)
    assert entry is not None
    det, idx = entry
    assert idx == 1
    assert det["source_ids"] == [0, 2]


def test_detector_rois_for_source_nested():
    body = _sample_body()
    rois = detector_rois_for_source(body, 2)
    assert len(rois) == 2
    assert rois[0] == [500.0, 0.0, 400.0, 300.0]


def test_ui_rois_round_trip():
    body = _sample_body()
    ui = ui_rois_from_detector(body, 0)
    assert len(ui) == 1
    x1, y1, x2, y2 = ui[0]
    assert x1 == pytest.approx(100 / 1920, rel=1e-3)
    assert y2 == pytest.approx((50 + 100) / 1080, rel=1e-3)

    body2 = {
        "pipeline": {
            "sources": [{"source_ids": [0], "source_names": ["Cam1"], "frame_width": 1920, "frame_height": 1080}],
            "detectors": [{"source_ids": [0], "roi": [[]]}],
        }
    }
    stored = ui_rois_to_detector(body2, 0, ui)
    assert stored[0][0] == 100
    assert stored[0][1] == 50
    assert stored[0][2] in (200, 201)
    assert stored[0][3] in (100, 101)
    set_detector_rois_for_source(body2, 0, stored)
    reread = detector_rois_for_source(body2, 0)
    assert reread[0][0] == 100.0
    assert reread[0][1] == 50.0
    assert reread[0][2] in (200.0, 201.0)
    assert reread[0][3] in (100.0, 101.0)


def test_xywh_list_to_xyxy_int_inclusive():
    out = xywh_list_to_xyxy_int([[10, 20, 30, 40]])
    assert out == [[10, 20, 39, 59]]


def test_ui_rois_from_detector_split_source_uses_crop_size():
    body = {
        "pipeline": {
            "sources": [
                {
                    "split": True,
                    "source_ids": [1, 2],
                    "source_names": ["Cam2", "Cam3"],
                    "src_coords": [
                        [0, 0, 2304, 1300],
                        [0, 1300, 2304, 1292],
                    ],
                }
            ],
            "detectors": [
                {
                    "source_ids": [2],
                    "roi": [[[0, 0, 2304, 1292]]],
                }
            ],
        }
    }
    ui = ui_rois_from_detector(body, 2)
    assert len(ui) == 1
    assert ui[0] == pytest.approx([0.0, 0.0, 1.0, 1.0], rel=1e-3)
