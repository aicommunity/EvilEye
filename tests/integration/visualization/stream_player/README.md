# Stream player integration tests

GUI and playback checks for stream recording player widgets.

## Conventions

- **`stream_player_project_root`** / **`stream_player_data_dir`** (`conftest.py`) — shared paths; do not duplicate `sys.path` bootstrap in new tests.
- Prefer **`qapp`** pytest-qt fixture instead of creating `QApplication(sys.argv)` per file.
- Timer/diagnostic tests are split by depth (`test_stream_player_timer_*`); run the subset you need locally.
