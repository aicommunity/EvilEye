from __future__ import annotations

from evileye.api.core.journal_grouping import group_objects_rows
from evileye.api.core import journal_service as js


def test_merge_prepend_logic_break_on_overlap():
    """Qt-parity: stop at first overlapping key in incoming prefix."""
    existing = [
        {"time": "t2", "event": "E", "information": "b", "row_key": "t2|E|b"},
        {"time": "t1", "event": "E", "information": "a", "row_key": "t1|E|a"},
    ]
    incoming = [
        {"time": "t3", "event": "E", "information": "c", "row_key": "t3|E|c"},
        {"time": "t2", "event": "E", "information": "b", "row_key": "t2|E|b"},
        {"time": "t0", "event": "E", "information": "z", "row_key": "t0|E|z"},
    ]
    compare_len = max(1, len(incoming))
    existing_keys = {r["row_key"] for r in existing[:compare_len]}
    fresh = []
    for row in incoming:
        if row["row_key"] in existing_keys:
            break
        fresh.append(row)
    assert len(fresh) == 1
    assert fresh[0]["row_key"] == "t3|E|c"


def test_merge_current_filters_skips_source_names_for_events(monkeypatch):
    monkeypatch.setattr(js, "_current_source_names", lambda: {"Cam1", "Cam2"})
    events = js._merge_current_filters({}, journal_kind="events")
    assert "source_names" not in events
    objects = js._merge_current_filters({}, journal_kind="objects")
    assert objects["source_names"] == ["Cam1", "Cam2"]


def test_merge_current_filters_respects_explicit_source_name(monkeypatch):
    monkeypatch.setattr(js, "_current_source_names", lambda: {"Cam1", "Cam2"})
    merged = js._merge_current_filters({"source_name": "Cam1"}, journal_kind="objects")
    assert "source_names" not in merged
    assert merged["source_name"] == "Cam1"

