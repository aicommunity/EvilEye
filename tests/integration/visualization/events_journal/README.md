# Events journal integration tests

GUI and JSON journal checks for `EventsJournalJson`, data sources, and related widgets.

## Conventions

- **`journal_test_logger`** (`conftest.py`) — use instead of per-file `setup_evileye_logging`.
- **`journal_base_dir`** — session `EvilEyeData` path from project root.
- **`helpers.py`** — `journal_today_folder`, `write_json`, `EXPECTED_JOURNAL_HEADERS`, `table_horizontal_headers`, `load_db_config`.
- Prefer **`qapp`** pytest-qt fixture; do not create `QApplication(sys.argv)` in tests.
- Column layout tests should use `EXPECTED_JOURNAL_HEADERS` and real `assert` checks.

Log-only exploratory tests remain for manual debugging; new tests should assert behavior.
