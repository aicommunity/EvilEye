"""Shared fixtures for stream player integration tests."""

import sys
from pathlib import Path

import pytest

# Project root (tests/integration/visualization/stream_player -> 5 parents)
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


@pytest.fixture(scope="session")
def stream_player_project_root():
    return _PROJECT_ROOT


@pytest.fixture(scope="module")
def stream_player_data_dir(evil_eye_data_dir):
    """Absolute EvilEyeData path for stream player tests."""
    return str(evil_eye_data_dir)
