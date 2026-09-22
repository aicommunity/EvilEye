#!/usr/bin/env python3
"""Ensure playback-test user exists (role=user, allowed_cameras).

Requires admin credentials via env:
  EVILEYE_E2E_BASE, EVILEYE_E2E_ADMIN_USER, EVILEYE_E2E_ADMIN_PASSWORD
  EVILEYE_E2E_USER (default playback-test@local)
  EVILEYE_E2E_PASSWORD (required for create)
  E2E_PLAYBACK_CAMERAS (comma-separated, default Cam1,Cam2)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("EVILEYE_E2E_BASE", "http://127.0.0.1:8181").rstrip("/")
ADMIN_USER = os.environ.get("EVILEYE_E2E_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("EVILEYE_E2E_ADMIN_PASSWORD", os.environ.get("EVILEYE_E2E_PASSWORD", "admin"))
TEST_USER = os.environ.get("EVILEYE_E2E_USER", "playback-test@example.com")
TEST_PASSWORD = os.environ.get("EVILEYE_E2E_PASSWORD", "")
CAMERAS = [c.strip() for c in os.environ.get("E2E_PLAYBACK_CAMERAS", "Cam1,Cam2").split(",") if c.strip()]


def _request(method: str, path: str, body: dict | None = None, cookie: str = "") -> tuple[int, str, dict[str, str]]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", "replace")
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, raw, headers
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace") if exc.fp else ""
        headers = {k.lower(): v for k, v in exc.headers.items()}
        return exc.code, raw, headers


def _login(username: str, password: str) -> str:
    code, raw, headers = _request("POST", "/api/v1/auth/login", {"username": username, "password": password})
    if code != 200:
        raise RuntimeError(f"login failed for {username}: http {code} {raw[:200]}")
    set_cookie = headers.get("set-cookie", "")
    return set_cookie.split(";")[0] if set_cookie else ""


def main() -> int:
    if not TEST_PASSWORD:
        print("ERROR: set EVILEYE_E2E_PASSWORD for the test user", file=sys.stderr)
        return 2

    print(f"BASE={BASE} TEST_USER={TEST_USER} CAMERAS={CAMERAS}")
    admin_cookie = _login(ADMIN_USER, ADMIN_PASSWORD)

    code, raw, _ = _request("GET", "/api/v1/users", cookie=admin_cookie)
    if code != 200:
        print(f"WARN: cannot list users (http {code})", file=sys.stderr)
    else:
        try:
            users = json.loads(raw)
            items = users if isinstance(users, list) else users.get("items") or users.get("users") or []
            for u in items:
                email = (u.get("email") or u.get("username") or "").lower()
                if email == TEST_USER.lower():
                    print(f"User already exists: {TEST_USER}")
                    cams = u.get("allowed_cameras") or []
                    if not cams and CAMERAS:
                        patch_code, patch_raw, _ = _request(
                            "PATCH",
                            f"/api/v1/users/{TEST_USER}",
                            {"allowed_cameras": CAMERAS},
                            cookie=admin_cookie,
                        )
                        if patch_code == 200:
                            print(f"Patched allowed_cameras={CAMERAS}")
                        else:
                            print(f"WARN: PATCH allowed_cameras failed http {patch_code}: {patch_raw[:200]}", file=sys.stderr)
                    try:
                        _login(TEST_USER, TEST_PASSWORD)
                        print("Login OK")
                    except RuntimeError as exc:
                        print(f"WARN: {exc}", file=sys.stderr)
                    return 0
        except json.JSONDecodeError:
            pass

    payload = {
        "email": TEST_USER,
        "password": TEST_PASSWORD,
        "role": "user",
        "allowed_cameras": CAMERAS,
    }
    code, raw, _ = _request("POST", "/api/v1/users", payload, cookie=admin_cookie)
    if code not in (200, 201):
        print(f"ERROR: create user failed http {code}: {raw[:300]}", file=sys.stderr)
        return 1

    print(f"Created user {TEST_USER} with allowed_cameras={CAMERAS}")
    try:
        body = json.loads(raw)
        created_cams = (body.get("user") or {}).get("allowed_cameras") or []
        if not created_cams and CAMERAS:
            patch_code, patch_raw, _ = _request(
                "PATCH",
                f"/api/v1/users/{TEST_USER}",
                {"allowed_cameras": CAMERAS},
                cookie=admin_cookie,
            )
            if patch_code != 200:
                print(f"WARN: PATCH allowed_cameras failed http {patch_code}: {patch_raw[:200]}", file=sys.stderr)
            else:
                print(f"Patched allowed_cameras={CAMERAS}")
    except json.JSONDecodeError:
        pass
    _login(TEST_USER, TEST_PASSWORD)
    print("Login OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
