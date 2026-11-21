#!/usr/bin/env python3
"""Start an isolated EvilEye site that raises real alarms, for the browser alarm check.

Creates ``<site>/credentials.json`` with three *test* users (admin, a user limited to the
camera that raises alarms, and a user with no cameras), a config derived from
``configs/hardhat_1cam.json`` with an all-day alarm schedule for persons, and starts the
pipeline with the Web UI on ``127.0.0.1:<port>``. Passwords are random and only written to
``<site>/e2e_users.json`` (mode 0600). Run ``tests/e2e/alarm_browser.spec.ts`` against it, then
``alarm_browser_setup.py --stop``.

    python scripts/alarm_browser_setup.py --video videos/x.mp4 --site /tmp/eye9b --port 18181
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAMERA = "Cam1"


def make_credentials(site: Path) -> dict:
    sys.path.insert(0, str(ROOT))
    from evileye.api.security import hash_password

    users = {
        "e2e_admin": {"role": "admin", "allowed_cameras": []},
        "e2e_cam1": {"role": "user", "allowed_cameras": [CAMERA]},
        "e2e_nocam": {"role": "user", "allowed_cameras": []},
    }
    passwords = {name: secrets.token_urlsafe(18) for name in users}
    web_auth = {
        "enabled": True,
        "session_secret": secrets.token_urlsafe(48),
        "internal_token": secrets.token_urlsafe(24),
        "secure_cookies": False,
        "protection": {"enabled": True, "whitelist_ips": ["127.0.0.1", "::1"]},
        "users": [
            {"username": name, "password_hash": hash_password(passwords[name]), "disabled": False, **meta}
            for name, meta in users.items()
        ],
    }
    (site / "credentials.json").write_text(json.dumps({"web_auth": web_auth}, indent=2), encoding="utf-8")
    secret_file = site / "e2e_users.json"
    secret_file.write_text(json.dumps(passwords), encoding="utf-8")
    os.chmod(secret_file, 0o600)
    return passwords


def make_config(site: Path, video: str, port: int) -> Path:
    cfg = json.loads((ROOT / "configs" / "hardhat_1cam.json").read_text(encoding="utf-8"))
    cfg = copy.deepcopy(cfg)
    source = cfg["pipeline"]["sources"][0]
    source.update({"camera": video, "source_names": [CAMERA], "source_ids": [0], "loop_play": True})
    for detector in cfg["pipeline"]["detectors"]:
        detector["roi"] = [[]]
    cfg["controller"].update({"gui_enabled": False, "show_main_gui": False, "autoclose": False, "auto_restart": False})
    cfg["record"].update({"enabled": False, "continuous_recording_enabled": False})
    cfg["storage_monitor"]["enabled"] = False
    cfg["server"].update({"enabled": True, "host": "127.0.0.1", "port": port, "execution_mode": "process"})
    cfg.setdefault("database", {})["image_dir"] = str(site / "EvilEyeData")
    detectors = cfg.setdefault("events_detectors", {})
    schedule = detectors.setdefault("ScheduleAlarmEventsDetector", {})
    schedule["default_schedule"] = {
        "enabled": True,
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "periods": [["00:00", "23:59"]],
        "class_ids": [0],
    }
    schedule["sources"] = {}
    path = site / "configs" / "alarm_browser.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return path


def stop(site: Path) -> None:
    # Pipelines started through the Web API are children of the web server, not of this script.
    subprocess.run(["pkill", "-f", str(site / "configs" / "alarm_browser.json")], check=False)
    for name in ("eyes.pid", "web.pid"):
        pid_file = site / name
        if pid_file.exists():
            try:
                os.killpg(int(pid_file.read_text()), signal.SIGTERM)
            except (ProcessLookupError, ValueError):
                pass
            pid_file.unlink(missing_ok=True)


def start_run(site: Path, port: int) -> int:
    """Create and start the config run as ``e2e_admin`` through the Web API (like the Runs page)."""
    import http.cookiejar
    import urllib.request

    passwords = json.loads((site / "e2e_users.json").read_text(encoding="utf-8"))
    base = f"http://127.0.0.1:{port}/api/v1"
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(path: str, payload: dict | None = None) -> dict:
        request = urllib.request.Request(
            base + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST" if payload is not None or path.endswith("/start") else "GET",
        )
        return json.loads(opener.open(request, timeout=60).read().decode() or "{}")

    call("/auth/login", {"username": "e2e_admin", "password": passwords["e2e_admin"]})
    run = call("/configs/runs", {"name": "alarm-browser-check", "config_name": "alarm_browser.json"})
    run_id = run.get("id") or run.get("rid") or run.get("run_id")
    started = call(f"/configs/runs/{run_id}/start", {})
    print(json.dumps({"run_id": run_id, "state": started.get("state"), "keys": sorted(started)[:8]}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--site", default="/tmp/eye9b")
    parser.add_argument("--port", type=int, default=18181)
    parser.add_argument("--video")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument(
        "--direct", action="store_true",
        help="start the pipeline directly instead of through the Web UI 'Runs' API",
    )
    parser.add_argument("--start-run", action="store_true", help="start the config run through the Web API")
    args = parser.parse_args()
    site = Path(args.site)
    if args.stop:
        stop(site)
        return 0
    if args.start_run:
        return start_run(site, args.port)
    if not args.video:
        parser.error("--video is required")
    stop(site)
    site.mkdir(parents=True, exist_ok=True)
    data = site / "EvilEyeData"
    data.mkdir(exist_ok=True)
    run_dir = site / "run"
    run_dir.mkdir(mode=0o700, exist_ok=True)
    make_credentials(site)
    # Relative paths in configs (models, trackers) resolve against the site directory.
    for name in ("models",):
        link = site / name
        if not link.exists():
            link.symlink_to(ROOT / name, target_is_directory=True)
    config = make_config(site, args.video, args.port)
    env = dict(
        os.environ,
        EVILEYE_SITE_DIR=str(site),
        EVILEYE_DATA_DIR=str(data),
        XDG_RUNTIME_DIR=str(run_dir),
        QT_QPA_PLATFORM="offscreen",
        EVILEYE_HTTP_PORT=str(args.port),
    )
    proc = None
    if args.direct:
        log = open(site / "evileye.log", "w", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, "-m", "evileye.process", "--config", str(config), "--no-gui", "--log-level", "INFO"],
            cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
        (site / "eyes.pid").write_text(str(proc.pid))
    # An active OS service makes the pipeline skip its embedded web server, so serve it here.
    web = subprocess.Popen(
        [sys.executable, "-m", "evileye.server", "--host", "127.0.0.1", "--port", str(args.port), "--no-reload"],
        cwd=str(ROOT), env=env, stdout=open(site / "web.log", "w", encoding="utf-8"),
        stderr=subprocess.STDOUT, start_new_session=True,
    )
    (site / "web.pid").write_text(str(web.pid))
    print(json.dumps({"pid": proc.pid if proc else None, "web_pid": web.pid, "site": str(site), "port": args.port,
                      "log": str(site / "evileye.log")}))
    time.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
