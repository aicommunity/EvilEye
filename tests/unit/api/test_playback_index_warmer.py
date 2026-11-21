"""Continuous playback index warmer helpers."""

from __future__ import annotations

from datetime import date, timedelta

from evileye.api.core import playback_index_warmer as warmer


def test_prioritize_dates_puts_today_and_yesterday_first():
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    older = (date.today() - timedelta(days=5)).isoformat()
    older2 = (date.today() - timedelta(days=3)).isoformat()
    ordered = warmer._prioritize_dates([older, today, older2, yesterday])
    assert ordered[0] == today
    assert ordered[1] == yesterday
    assert ordered[2:] == sorted([older, older2], reverse=True)


def test_prioritize_dates_empty():
    assert warmer._prioritize_dates([]) == []


def test_recent_dates_limit():
    dates = [f"2026-01-{i:02d}" for i in range(1, 20)]
    recent = warmer._recent_dates(dates, limit=3)
    assert recent == dates[-3:]
