"""Shared fixtures for events journal integration tests."""

import pytest
from evileye.core.logger import get_module_logger


@pytest.fixture(scope="module")
def journal_test_logger():
    return get_module_logger("events_journal.integration")
