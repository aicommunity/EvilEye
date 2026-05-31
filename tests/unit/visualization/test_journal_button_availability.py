"""Unit tests for journal action availability (MainWindow logic)."""

import pytest

from tests.integration.visualization.events_journal.helpers import journal_actions_available


@pytest.mark.parametrize(
    "db_journal_win,deferred,expected",
    [
        ("EventsJournalJson", None, True),
        (object(), None, True),
        (None, {"enabled": True, "created": False}, True),
        (None, {"enabled": True, "created": True}, False),
        (None, {"enabled": False, "created": False}, False),
        (None, None, False),
        (None, "not-a-dict", False),
    ],
)
def test_journal_actions_available(db_journal_win, deferred, expected):
    assert journal_actions_available(db_journal_win, deferred) is expected
