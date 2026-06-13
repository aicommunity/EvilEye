"""Shared fixtures for events journal integration tests."""

import pytest
from evileye.core.logger import get_module_logger


@pytest.fixture(scope="module")
def journal_test_logger():
    return get_module_logger("events_journal.integration")


@pytest.fixture
def journal_base_dir(evil_eye_data_dir):
    """Absolute path to EvilEyeData for journal JSON tests."""
    return str(evil_eye_data_dir)
