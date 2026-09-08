import os

import pytest

from evileye.api.core.client_debug import (
    clear_client_debug_cache,
    user_client_debug_enabled,
)


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    clear_client_debug_cache()
    monkeypatch.delenv("EVILEYE_CLIENT_DEBUG_USERS", raising=False)
    yield
    clear_client_debug_cache()


def test_default_allowlist_admin_and_onmatsko():
    assert user_client_debug_enabled("admin") is True
    assert user_client_debug_enabled("onmatsko@gmail.com") is True
    assert user_client_debug_enabled("e2e-playback@example.com") is True
    assert user_client_debug_enabled("playback-test@example.com") is True


def test_substring_omatsko():
    assert user_client_debug_enabled("OMatsko.local") is True
    assert user_client_debug_enabled("user-onmatsko") is True


def test_random_user_off():
    assert user_client_debug_enabled("someone@example.com") is False
    assert user_client_debug_enabled("") is False
    assert user_client_debug_enabled(None) is False


def test_env_merge(monkeypatch):
    monkeypatch.setenv("EVILEYE_CLIENT_DEBUG_USERS", "diag@example.com, ExtraUser")
    clear_client_debug_cache()
    assert user_client_debug_enabled("diag@example.com") is True
    assert user_client_debug_enabled("extrauser") is True
    assert user_client_debug_enabled("admin") is True
