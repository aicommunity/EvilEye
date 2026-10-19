"""Password re-entry before plugin installation is rate limited per user and address."""
from __future__ import annotations

import json

import pytest

from evileye.api.routes import extensions as routes
from tests.unit.api.test_builder_access_stage2 import loopback  # noqa: F401  (fixture)
from tests.unit.api.test_security_hardening import secured_client  # noqa: F401  (fixture)

URL = "/api/v1/admin/extensions/plugins"
GOOD = {"name": "demo", "template": "processor", "password": "correct-horse"}
BAD = {"name": "demo", "template": "processor", "password": "wrong"}


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture()
def clock(monkeypatch):
    fake = _Clock()
    routes.reset_password_limiter_for_tests(routes._PasswordAttemptLimiter(clock=fake))
    created = []
    monkeypatch.setattr(routes, "create_plugin_operation", lambda name, template: created.append(name) or {"id": "x"})
    yield fake, created
    routes.reset_password_limiter_for_tests()


def test_five_wrong_passwords_lock_the_action_even_for_the_right_password(loopback, clock):  # noqa: F811
    local, _ = loopback
    fake, created = clock

    statuses = [local.post(URL, json=BAD).status_code for _ in range(4)]
    assert statuses == [403, 403, 403, 403]
    locked = local.post(URL, json=BAD)
    assert locked.status_code == 429
    assert int(locked.headers["Retry-After"]) == 900
    assert "try again" in locked.json()["detail"]

    blocked = local.post(URL, json=GOOD)
    assert blocked.status_code == 429 and created == []

    fake.now += 899
    assert local.post(URL, json=GOOD).status_code == 429
    fake.now += 3
    assert local.post(URL, json=GOOD).status_code == 200
    assert created == ["demo"]


def test_a_correct_password_resets_the_failure_counter(loopback, clock):  # noqa: F811
    local, _ = loopback
    for _ in range(4):
        assert local.post(URL, json=BAD).status_code == 403
    assert local.post(URL, json=GOOD).status_code == 200
    for _ in range(4):
        assert local.post(URL, json=BAD).status_code == 403  # would be locked without the reset


def test_old_failures_leave_the_window(loopback, clock):  # noqa: F811
    local, _ = loopback
    fake, _ = clock
    for _ in range(4):
        assert local.post(URL, json=BAD).status_code == 403
    fake.now += 301  # default window is 300 s
    assert local.post(URL, json=BAD).status_code == 403
    assert local.post(URL, json=GOOD).status_code == 200


def test_limits_are_configurable_in_credentials(loopback, clock):  # noqa: F811
    local, tmp_path = loopback
    path = tmp_path / "credentials.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["web_auth"]["protection"].update(
        {"builder_password_max_failures": 2, "builder_password_lock_sec": 60}
    )
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert local.post(URL, json=BAD).status_code == 403
    response = local.post(URL, json=BAD)
    assert response.status_code == 429 and response.headers["Retry-After"] == "60"


def test_lock_follows_the_user_across_client_addresses(loopback, clock):  # noqa: F811
    from fastapi.testclient import TestClient

    local, tmp_path = loopback
    path = tmp_path / "credentials.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["web_auth"]["protection"]["builder_allowed_ips"] = ["203.0.113.0/24"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    for _ in range(5):
        local.post(URL, json=BAD)
    other = TestClient(local.app, client=("203.0.113.9", 50000))
    assert other.post("/api/v1/auth/login", json={"username": "admin", "password": "correct-horse"}).status_code == 200
    assert other.post(URL, json=GOOD).status_code == 429


def test_limiter_unit_keys_are_independent():
    fake = _Clock()
    limiter = routes._PasswordAttemptLimiter(clock=fake)
    for _ in range(2):
        limiter.record_failure(["user:a", "ip:1"], max_failures=3, window_sec=60, lock_sec=30)
    assert limiter.retry_after(["user:a"]) == 0
    assert limiter.record_failure(["user:a", "ip:1"], max_failures=3, window_sec=60, lock_sec=30) == 30
    assert limiter.retry_after(["user:b", "ip:1"]) > 0  # the address key is locked too
    assert limiter.retry_after(["user:b", "ip:2"]) == 0
    fake.now += 31
    assert limiter.retry_after(["user:a", "ip:1"]) == 0
