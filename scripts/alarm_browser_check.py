#!/usr/bin/env python3
"""Check in a real browser that an alarm is shown according to the camera ACL.

Run against the site started by ``scripts/alarm_browser_setup.py`` (and a running config
run, ``--start-run``). The three test users' passwords are read from the JSON in
``EVILEYE_E2E_PASSWORDS`` ({user: password}); nothing is printed about them.

    EVILEYE_E2E_BASE=http://127.0.0.1:18181 EVILEYE_E2E_PASSWORDS='{...}' \
        python scripts/alarm_browser_check.py --shots out/

Expectations: ``e2e_admin`` and ``e2e_cam1`` see the ScheduleAlarmEvent of camera ``Cam1``;
``e2e_cam1`` sees no other camera's events; ``e2e_nocam`` sees no alarm. Exit code 0 on pass.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ALARM = re.compile(r"ScheduleAlarmEvent")
CASES = {
    "e2e_admin": {"alarm": True, "must_contain": ["Cam1"], "must_not_contain": []},
    "e2e_cam1": {"alarm": True, "must_contain": ["Cam1"], "must_not_contain": ["System started"]},
    "e2e_nocam": {"alarm": False, "must_contain": [], "must_not_contain": []},
}


def page_text(page, base: str, wait_for_alarm: bool) -> str:
    deadline = time.monotonic() + (60 if wait_for_alarm else 8)
    text = ""
    while time.monotonic() < deadline:
        page.goto(f"{base}/events", wait_until="networkidle")
        page.wait_for_timeout(1500)
        text = " ".join(page.locator("body").inner_text().split())
        if not wait_for_alarm or ALARM.search(text):
            break
        page.wait_for_timeout(3000)
    return text


def sign_in(page, base: str, user: str, password: str) -> None:
    page.goto(f"{base}/events", wait_until="domcontentloaded")
    username = page.locator('input[autocomplete="username"]')
    username.wait_for(state="visible", timeout=15_000)
    username.fill(user)
    secret = page.locator('input[autocomplete="current-password"]')
    secret.fill(password)
    secret.press("Enter")
    username.wait_for(state="detached", timeout=15_000)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default=os.environ.get("EVILEYE_E2E_BASE", "http://127.0.0.1:18181"))
    parser.add_argument("--shots", help="directory for screenshots")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    passwords = json.loads(os.environ.get("EVILEYE_E2E_PASSWORDS") or "{}")
    if not passwords:
        print("EVILEYE_E2E_PASSWORDS is not set", file=sys.stderr)
        return 2

    from playwright.sync_api import sync_playwright

    shots = Path(args.shots) if args.shots else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        try:
            for user, expect in CASES.items():
                context = browser.new_context(viewport={"width": 1500, "height": 900})
                page = context.new_page()
                try:
                    sign_in(page, args.base, user, passwords[user])
                    text = page_text(page, args.base, wait_for_alarm=expect["alarm"])
                    if shots:
                        page.screenshot(path=str(shots / f"{user}-events.png"), full_page=True)
                    checks = {
                        "alarm_visible": bool(ALARM.search(text)) == expect["alarm"],
                        **{f"shows_{item}": item in text for item in expect["must_contain"]},
                        **{f"hides_{item}": item not in text for item in expect["must_not_contain"]},
                    }
                except Exception as exc:  # noqa: BLE001
                    checks = {"error": False}
                    print(f"{user}: {type(exc).__name__}: {str(exc)[:200]}", file=sys.stderr)
                finally:
                    context.close()
                results[user] = checks
        finally:
            browser.close()

    print(json.dumps(results, indent=2))
    return 0 if all(all(checks.values()) for checks in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
