"""TD-AUD-SQL-ID: journal adapter table_name whitelist."""

from __future__ import annotations

import pytest

from evileye.visualization_modules.journal_adapters.jadapter_base import JournalAdapterBase
from evileye.visualization_modules.journal_adapters.jadapter_fov_events import (
    JournalAdapterFieldOfViewEvents,
)


class TestTableWhitelist:
    def test_known_table_is_accepted(self):
        adapter = JournalAdapterFieldOfViewEvents()
        adapter.set_params(table_name="schedule_alarm_events")
        assert adapter.table_name == "schedule_alarm_events"

    def test_unknown_table_is_rejected(self):
        adapter = JournalAdapterFieldOfViewEvents()
        with pytest.raises(ValueError, match="not a known event table"):
            adapter.set_params(table_name="zone_events; DROP TABLE objects")

    def test_missing_table_keeps_none(self):
        adapter = JournalAdapterFieldOfViewEvents()
        adapter.set_params()
        assert adapter.table_name is None
