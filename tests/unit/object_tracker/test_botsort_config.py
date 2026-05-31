"""Shared BoTSORT config module."""

import pytest

from evileye.object_tracker.botsort_config import BostSortCfg, botsort_cfg_from_dict


@pytest.mark.unit
def test_botsort_cfg_from_dict_filters_unknown_keys():
    cfg = botsort_cfg_from_dict({"match_thresh": 0.9, "unknown": 1})
    assert cfg.match_thresh == 0.9
    assert cfg.tracker_type == "botsort"


@pytest.mark.unit
def test_bost_sort_cfg_defaults():
    cfg = BostSortCfg()
    assert cfg.with_reid is False
    assert cfg.track_buffer == 30
