"""Native Windows (and cross-platform) watchdog for host pip deployments."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from evileye.core.paths import logs_dir, monitor_dir, site_root
from evileye.core.process_control import find_pids_by_cmdline_regex, pid_exists, terminate_tree

LOG_STALE_SEC = int(os.environ.get("EVILEYE_WATCHDOG_LOG_STALE_SEC", "600"))
RESTART_GRACE_SEC = int(os.environ.get("EVILEYE_WATCHDOG_GRACE_SEC", "900"))
RESTART_BACKOFF_BASE = int(os.environ.get("EVILEYE_WATCHDOG_BACKOFF_BASE", "300"))
RESTART_BACKOFF_MAX = int(os.environ.get("EVILEYE_WATCHDOG_BACKOFF_MAX", "3600"))
TASK_NAME = "EvilEyeWatchdog"
MORNING_TASK_NAME = "EvilEyeMorningReport"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _ensure_monitor(root: Path) -> Path:
    mdir = monitor_dir(root)
    (mdir / "incidents").mkdir(parents=True, exist_ok=True)
    (mdir / "reports").mkdir(parents=True, exist_ok=True)
    return mdir


def _append_journal(mdir: Path, entry: dict[str, Any]) -> None:
    path = mdir / "journal.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _write_state(mdir: Path, payload: dict[str, Any]) -> None:
    payload = dict(payload)
    payload["updated_at"] = _now_iso()
    (mdir / "state.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _log_watchdog(mdir: Path, message: str) -> None:
    line = f"{_now_iso()} {message}\n"
    with (mdir / "watchdog.log").open("a", encoding="utf-8") as handle:
        handle.write(line)


def _config_stem(config: str) -> str:
    name = Path(config).name
    if name.endswith(".json"):
        name = name[:-5]
    return name


def _latest_main_log(root: Path) -> Optional[Path]:
    log_root = logs_dir(root)
    if not log_root.exists():
        return None
    files = sorted(log_root.glob("*_evileye_main.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _grace_active(mdir: Path) -> bool:
    marker = mdir / ".restart_grace_until"
    if not marker.exists():
        return False
    try:
        until = float(marker.read_text(encoding="utf-8").strip())
        return time.time() < until
    except Exception:
        return False


def _set_grace(mdir: Path) -> None:
    (mdir / ".restart_grace_until").write_text(str(time.time() + RESTART_GRACE_SEC), encoding="utf-8")


def _backoff_blocked(mdir: Path) -> bool:
    marker = mdir / ".restart_backoff"
    if not marker.exists():
        return False
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        until = float(data.get("until", 0))
        return time.time() < until
    except Exception:
        return False


def _bump_backoff(mdir: Path) -> None:
    marker = mdir / ".restart_backoff"
    streak = 1
    if marker.exists():
        try:
            streak = int(json.loads(marker.read_text(encoding="utf-8")).get("streak", 0)) + 1
        except Exception:
            streak = 1
    delay = min(RESTART_BACKOFF_MAX, RESTART_BACKOFF_BASE * (2 ** max(0, streak - 1)))
    marker.write_text(
        json.dumps({"streak": streak, "until": time.time() + delay}, indent=2) + "\n",
        encoding="utf-8",
    )


def _reset_backoff(mdir: Path) -> None:
    marker = mdir / ".restart_backoff"
    if marker.exists():
        marker.unlink()


def manual_stop_active(root: Optional[Path] = None) -> bool:
    mdir = _ensure_monitor(site_root(root))
    marker = mdir / ".manual_stop_until"
    if not marker.exists():
        return False
    try:
        until = float(marker.read_text(encoding="utf-8").strip())
        return time.time() < until
    except Exception:
        return False


def restart_grace_active(root: Optional[Path] = None) -> bool:
    return _grace_active(_ensure_monitor(site_root(root)))


def set_manual_stop_cooldown(*, seconds: int = 3600, root: Optional[Path] = None) -> None:
    mdir = _ensure_monitor(site_root(root))
    until = time.time() + max(1, int(seconds))
    (mdir / ".manual_stop_until").write_text(str(until), encoding="utf-8")


def clear_manual_stop_cooldown(root: Optional[Path] = None) -> None:
    marker = _ensure_monitor(site_root(root)) / ".manual_stop_until"
    if marker.exists():
        marker.unlink()


def set_restart_grace(*, seconds: Optional[int] = None, root: Optional[Path] = None) -> None:
    mdir = _ensure_monitor(site_root(root))
    duration = RESTART_GRACE_SEC if seconds is None else max(1, int(seconds))
    (mdir / ".restart_grace_until").write_text(str(time.time() + duration), encoding="utf-8")


def stop_evileye_run_scope() -> None:
    if not sys.platform.startswith("linux"):
        return
    if shutil.which("systemctl") is None:
        return
    subprocess.run(["systemctl", "--user", "stop", "evileye-run.scope"], check=False, capture_output=True)
    subprocess.run(["systemctl", "--user", "reset-failed", "evileye-run.scope"], check=False, capture_output=True)


def find_cli_and_child(config: str, root: Optional[Path] = None) -> tuple[Optional[int], Optional[int]]:
    stem = re.escape(_config_stem(config))
    cli_pids = find_pids_by_cmdline_regex([rf"evileye(\.exe)?\s+run.*{stem}", rf"cli_wrapper.*run.*{stem}"])
    child_pids = find_pids_by_cmdline_regex([rf"process\.py.*{stem}", rf"process_wrapper.*{stem}"])
    cli = cli_pids[0] if cli_pids else None
    child = child_pids[0] if child_pids else None
    return cli, child


def health_check(*, config: str, root: Optional[Path] = None, do_restart: bool = True) -> dict[str, Any]:
    site = site_root(root)
    mdir = _ensure_monitor(site)
    reasons: list[str] = []
    cli_pid, child_pid = find_cli_and_child(config)
    main_log = _latest_main_log(site)
    log_age = None
    if main_log is not None:
        log_age = int(time.time() - main_log.stat().st_mtime)

    grace = _grace_active(mdir)
    if cli_pid is None:
        reasons.append("cli_missing_during_restart_grace" if grace else "cli_process_missing")
    if child_pid is None:
        reasons.append("child_missing_during_restart_grace" if grace else "child_process_missing")
    if cli_pid and child_pid and log_age is not None and log_age > LOG_STALE_SEC and not grace:
        reasons.append(f"log_stale_{log_age}s")

    # Filter grace-only reasons as non-restart
    restart_reasons = [r for r in reasons if "during_restart_grace" not in r]
    status = "ok" if not reasons else ("incident" if restart_reasons else reasons[0])
    if not reasons:
        reasons = ["healthy"]
        status = "ok"

    entry = {
        "timestamp": _now_iso(),
        "status": status,
        "reason": ";".join(reasons),
        "cli_pid": str(cli_pid) if cli_pid else None,
        "child_pid": str(child_pid) if child_pid else None,
        "log_file": str(main_log) if main_log else None,
        "log_age_sec": log_age,
    }
    _append_journal(mdir, entry)
    _write_state(
        mdir,
        {
            "cli_pid": cli_pid,
            "child_pid": child_pid,
            "log_file": str(main_log) if main_log else None,
            "deploy_dir": str(site),
            "config": config,
            "last_status": status,
            "last_reason": entry["reason"],
        },
    )
    _log_watchdog(mdir, f"health status={status} reason={entry['reason']}")

    if status == "ok":
        _reset_backoff(mdir)
    elif do_restart and restart_reasons and not grace and not _backoff_blocked(mdir) and not manual_stop_active(site):
        incident_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        inc = mdir / "incidents" / incident_id
        inc.mkdir(parents=True, exist_ok=True)
        (inc / "summary.txt").write_text(entry["reason"] + "\n", encoding="utf-8")
        _log_watchdog(mdir, f"restarting due to {entry['reason']}")
        restart_evileye(config=config, root=site, reason=entry["reason"])
        _bump_backoff(mdir)

    return entry


def restart_evileye(*, config: str, root: Optional[Path] = None, reason: str = "watchdog_restart") -> bool:
    site = site_root(root)
    mdir = _ensure_monitor(site)
    lock = mdir / ".restart_lock"
    if lock.exists():
        try:
            if time.time() - lock.stat().st_mtime < 300:
                _log_watchdog(mdir, "restart skipped: lock fresh")
                return False
        except Exception:
            pass
    lock.write_text(_now_iso(), encoding="utf-8")
    (mdir / ".watchdog_restarting").write_text(_now_iso(), encoding="utf-8")

    cli_pid, child_pid = find_cli_and_child(config)
    for pid in (child_pid, cli_pid):
        if pid and pid_exists(pid):
            terminate_tree(pid, grace_sec=5.0)

    config_arg = config
    if not Path(config_arg).is_absolute():
        # Prefer path relative to site
        candidate = site / config_arg
        if candidate.exists():
            config_arg = str(candidate)

    creationflags = 0
    popen_kwargs: dict[str, Any] = {
        "cwd": str(site),
        "stdin": subprocess.DEVNULL,
        "stdout": open(mdir / "watchdog_stdout.log", "a", encoding="utf-8"),
        "stderr": subprocess.STDOUT,
    }
    if sys.platform.startswith("win"):
        creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        popen_kwargs["creationflags"] = creationflags
        popen_kwargs["close_fds"] = False
    else:
        popen_kwargs["start_new_session"] = True
        popen_kwargs["close_fds"] = True

    cmd = [sys.executable, "-m", "evileye.cli_wrapper", "run", config_arg, "--no-gui"]
    subprocess.Popen(cmd, **popen_kwargs)
    _set_grace(mdir)
    _log_watchdog(mdir, f"launched {' '.join(cmd)} reason={reason}")
    return True


def morning_report(*, root: Optional[Path] = None) -> Path:
    site = site_root(root)
    mdir = _ensure_monitor(site)
    day = datetime.now().strftime("%Y-%m-%d")
    report = mdir / "reports" / f"{day}.md"
    journal = mdir / "journal.jsonl"
    lines = [f"# EvilEye watchdog report {day}", ""]
    incidents = 0
    if journal.exists():
        for raw in journal.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(raw)
            except Exception:
                continue
            ts = str(row.get("timestamp") or "")
            if not ts.startswith(day):
                continue
            if row.get("status") == "incident":
                incidents += 1
            lines.append(f"- {ts}: {row.get('status')} — {row.get('reason')}")
    lines.insert(2, f"Incidents today: **{incidents}**")
    lines.insert(3, "")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _log_watchdog(mdir, f"morning report written {report}")
    return report


def install_watchdog(*, config: str, root: Optional[Path] = None, dry_run: bool = False) -> dict[str, Any]:
    site = site_root(root)
    mdir = _ensure_monitor(site)
    scripts = site / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    check_script = scripts / "evileye-watchdog-check.bat"
    morning_script = scripts / "evileye-watchdog-morning.bat"
    py = sys.executable
    check_body = (
        f'@echo off\r\n'
        f'cd /d "{site}"\r\n'
        f'"{py}" -m evileye.cli_wrapper watchdog-check --config "{config}"\r\n'
    )
    morning_body = (
        f'@echo off\r\n'
        f'cd /d "{site}"\r\n'
        f'"{py}" -m evileye.cli_wrapper watchdog-morning\r\n'
    )
    result = {
        "backend": "windows-task" if sys.platform.startswith("win") else "manual",
        "check_script": str(check_script),
        "morning_script": str(morning_script),
        "dry_run": dry_run,
        "config": config,
        "site_dir": str(site),
    }
    if dry_run:
        return result
    check_script.write_text(check_body, encoding="utf-8")
    morning_script.write_text(morning_body, encoding="utf-8")
    if sys.platform.startswith("win"):
        subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], check=False, capture_output=True)
        subprocess.run(["schtasks", "/Delete", "/TN", MORNING_TASK_NAME, "/F"], check=False, capture_output=True)
        create = subprocess.run(
            [
                "schtasks",
                "/Create",
                "/TN",
                TASK_NAME,
                "/TR",
                str(check_script),
                "/SC",
                "MINUTE",
                "/MO",
                "5",
                "/RL",
                "HIGHEST",
                "/F",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if create.returncode != 0:
            raise RuntimeError(create.stderr or create.stdout or "schtasks create failed")
        subprocess.run(
            [
                "schtasks",
                "/Create",
                "/TN",
                MORNING_TASK_NAME,
                "/TR",
                str(morning_script),
                "/SC",
                "DAILY",
                "/ST",
                "09:00",
                "/RL",
                "HIGHEST",
                "/F",
            ],
            check=False,
            capture_output=True,
        )
    (mdir / "watchdog_install.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    _log_watchdog(mdir, f"watchdog installed for config={config}")
    return result


def uninstall_watchdog(*, root: Optional[Path] = None, dry_run: bool = False) -> bool:
    site = site_root(root)
    if dry_run:
        return True
    if sys.platform.startswith("win"):
        subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], check=False, capture_output=True)
        subprocess.run(["schtasks", "/Delete", "/TN", MORNING_TASK_NAME, "/F"], check=False, capture_output=True)
    for name in ("evileye-watchdog-check.bat", "evileye-watchdog-morning.bat"):
        path = site / "scripts" / name
        if path.exists():
            path.unlink()
    return True
