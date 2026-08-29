"""Windows best-effort service backend for EvilEye web server."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class WindowsServiceError(RuntimeError):
    pass


@dataclass
class WindowsInstallResult:
    backend: str
    unit_path: Path
    service_name: str
    script_path: Path
    dry_run: bool = False


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def _build_start_script(
    site_dir: Path,
    *,
    python_exe: str,
    host: str,
    port: int,
    config: Optional[str],
    ssl_certfile: Optional[str] = None,
    ssl_keyfile: Optional[str] = None,
) -> str:
    config_arg = f' --config "{config}"' if config else ""
    ssl_arg = ""
    if ssl_certfile and ssl_keyfile:
        ssl_arg = f' --ssl-certfile "{ssl_certfile}" --ssl-keyfile "{ssl_keyfile}"'
    return (
        f'@echo off\r\n'
        f'cd /d "{site_dir}"\r\n'
        f'"{python_exe}" -m evileye.cli_wrapper server --host {host} --port {port} --no-reload{config_arg}{ssl_arg}\r\n'
    )


def install_windows(
    *,
    site_dir: Path,
    host: str = "0.0.0.0",
    port: int = 8181,
    config: Optional[str] = None,
    service_name: str = "EvilEye",
    dry_run: bool = False,
    ssl_certfile: Optional[str] = None,
    ssl_keyfile: Optional[str] = None,
) -> WindowsInstallResult:
    """Install via launcher .bat + Scheduled Task (best-effort, no NSSM)."""
    site_dir = site_dir.resolve()
    scripts = site_dir / "scripts"
    script_path = scripts / "evileye-server.bat"
    python_exe = sys.executable
    script_body = _build_start_script(
        site_dir,
        python_exe=python_exe,
        host=host,
        port=port,
        config=config,
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
    )
    backend = "windows-task"

    result = WindowsInstallResult(
        backend=backend,
        unit_path=script_path,
        service_name=service_name,
        script_path=script_path,
        dry_run=dry_run,
    )
    if dry_run:
        return result

    scripts.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script_body, encoding="utf-8")

    _run(["schtasks", "/Delete", "/TN", service_name, "/F"], check=False)
    create = _run(
        [
            "schtasks",
            "/Create",
            "/TN",
            service_name,
            "/TR",
            str(script_path),
            "/SC",
            "ONSTART",
            "/RL",
            "HIGHEST",
            "/F",
        ],
        check=False,
    )
    if create.returncode != 0:
        raise WindowsServiceError(
            "Failed to register Scheduled Task. Run as Administrator or start "
            f"manually: {script_path}\n{create.stderr or create.stdout}"
        )
    _run(["schtasks", "/Run", "/TN", service_name], check=False)
    return result


@dataclass
class WindowsControlResult:
    ok: bool
    message: str


def control_windows_service(action: str, *, service_name: str = "EvilEye") -> WindowsControlResult:
    action_norm = action.strip().lower()
    if action_norm == "start":
        proc = _run(["schtasks", "/Run", "/TN", service_name], check=False)
        ok = proc.returncode == 0
        msg = (proc.stdout or proc.stderr or "").strip() or f"schtasks /Run exit {proc.returncode}"
        return WindowsControlResult(ok=ok, message=msg)
    if action_norm == "stop":
        proc = _run(["schtasks", "/End", "/TN", service_name], check=False)
        ok = proc.returncode == 0
        msg = (proc.stdout or proc.stderr or "").strip() or f"schtasks /End exit {proc.returncode}"
        return WindowsControlResult(ok=ok, message=msg)
    if action_norm == "restart":
        _run(["schtasks", "/End", "/TN", service_name], check=False)
        proc = _run(["schtasks", "/Run", "/TN", service_name], check=False)
        ok = proc.returncode == 0
        msg = (proc.stdout or proc.stderr or "").strip() or f"schtasks restart exit {proc.returncode}"
        return WindowsControlResult(ok=ok, message=msg)
    if action_norm == "status":
        proc = _run(["schtasks", "/Query", "/TN", service_name, "/FO", "LIST"], check=False)
        ok = proc.returncode == 0
        msg = (proc.stdout or proc.stderr or "Task not found").strip()
        return WindowsControlResult(ok=ok, message=msg)
    raise WindowsServiceError(f"Unsupported Windows service action: {action}")


def uninstall_windows(
    *,
    site_dir: Path,
    service_name: str = "EvilEye",
    dry_run: bool = False,
) -> bool:
    site_dir = site_dir.resolve()
    script_path = site_dir / "scripts" / "evileye-server.bat"
    if dry_run:
        return script_path.exists()
    _run(["schtasks", "/Delete", "/TN", service_name, "/F"], check=False)
    removed = False
    if script_path.exists():
        script_path.unlink()
        removed = True
    return removed
