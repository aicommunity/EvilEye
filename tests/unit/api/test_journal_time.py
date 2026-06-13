from __future__ import annotations

import datetime

from evileye.api.core.journal_time import format_journal_timestamp, normalize_row_times, parse_journal_timestamp


def test_parse_journal_timestamp_iso():
    dt = parse_journal_timestamp("2026-06-13T13:29:06.606799")
    assert dt is not None
    assert dt.year == 2026
    assert dt.hour == 13
    assert dt.minute == 29


def test_format_journal_timestamp_adds_server_offset():
    formatted = format_journal_timestamp("2026-06-13T13:29:06")
    dt = datetime.datetime.fromisoformat(formatted)
    assert dt.tzinfo is not None
    assert dt.hour == 13
    assert dt.minute == 29


def test_normalize_row_times():
    row = normalize_row_times({"time": "2026-06-13T13:29:06", "time_lost": ""})
    assert "+" in row["time"] or row["time"].endswith("Z")
    assert row["time_lost"] == ""
