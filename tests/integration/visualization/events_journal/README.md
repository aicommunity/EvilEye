# Events journal integration tests

GUI and JSON journal checks for `EventsJournalJson`, data sources, and related widgets.

- Use `conftest.py` (`journal_test_logger`) instead of per-file `setup_evileye_logging` blocks.
- Use `helpers.py` for shared date folders and JSON fixtures.
- Prefer real assertions over log-only "documentation" tests.

Legacy duplicates were removed; former `tests/integration/journal/` tests live here.
