"""Tests for E2E staleness band helpers."""

import pytest

from scripts.measure_poly_e2e_fps import STALENESS_MAX, STALENESS_MIN, staleness_in_band


@pytest.mark.unit
def test_staleness_in_band_center():
    assert staleness_in_band(6.2) is True


@pytest.mark.unit
def test_staleness_in_band_edges():
    assert staleness_in_band(STALENESS_MIN) is True
    assert staleness_in_band(STALENESS_MAX) is True


@pytest.mark.unit
def test_staleness_too_fresh_disqualified():
    assert staleness_in_band(5.5) is False


@pytest.mark.unit
def test_staleness_too_stale_disqualified():
    assert staleness_in_band(6.6) is False


@pytest.mark.unit
def test_staleness_none():
    assert staleness_in_band(None) is False
