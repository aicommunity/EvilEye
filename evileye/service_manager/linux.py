"""Linux systemd backend for EvilEye web service."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class ServiceManagerError(RuntimeError):
    pass


@dataclass
class LinuxInstallResult:
    backend: str
    unit_path: Path
    service_name: str
    unit_text: str
    dry_run: bool = False


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def can_write_system_unit() -> bool:
    system_dir = Path("/etc/systemd/system")
    if not system_dir.is_dir():
        return False
    return os.access(system_dir, os.W_OK)


def resolve_mode(*, force_user: bool = False, force_system: bool = False) -> str:
    if force_user and force_system:
        raise ServiceManagerError("Cannot combine --user and --system")
    if force_system:
        if not can_write_system_unit():
            raise ServiceManagerError(
                "System unit directory is not writable; re-run with sudo or use --user"
            )
        return "systemd-system"
    if force_user:
        return "systemd-user"
    if can_write_system_unit():
        return "systemd-system"
    return "systemd-user"


def unit_path_for(backend: str, service_name: str = "evileye") -> Path:
    if backend == "systemd-system":
        return Path("/etc/systemd/system") / f"{service_name}.service"
    home = Path.home()
    return home / ".config" / "systemd" / "user" / f"{service_name}.service"


def systemctl_prefix(backend: str) -> list[str]:
    if backend == "systemd-user":
        return ["systemctl", "--user"]
    return ["systemctl"]


def install_linux(
    *,
    unit_text: str,
    backend: str,
    service_name: str = "evileye",
    dry_run: bool = False,
) -> LinuxInstallResult:
    if shutil.which("systemctl") is None:
        raise ServiceManagerError("systemctl not found; systemd is required on Linux")

    path = unit_path_for(backend, service_name)
    result = LinuxInstallResult(
        backend=backend,
        unit_path=path,
        service_name=service_name,
        unit_text=unit_text,
        dry_run=dry_run,
    )
    if dry_run:
        return result

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(unit_text, encoding="utf-8")

    prefix = systemctl_prefix(backend)
    _run([*prefix, "daemon-reload"])
    _run([*prefix, "enable", "--now", f"{service_name}.service"])
    return result


def uninstall_linux(
    *,
    backend: Optional[str] = None,
    unit_path: Optional[str | Path] = None,
    service_name: str = "evileye",
    dry_run: bool = False,
) -> bool:
    """Return True if something was removed / disabled."""
    if shutil.which("systemctl") is None:
        raise ServiceManagerError("systemctl not found; systemd is required on Linux")

    backends: list[str] = []
    if backend:
        backends = [backend]
    else:
        backends = ["systemd-user", "systemd-system"]

    removed = False
    for be in backends:
        prefix = systemctl_prefix(be)
        path = Path(unit_path) if unit_path and be == backend else unit_path_for(be, service_name)
        if dry_run:
            if path.exists():
                removed = True
            continue
        # disable/stop even if unit file missing
        _run([*prefix, "disable", "--now", f"{service_name}.service"], check=False)
        if path.exists():
            path.unlink()
            removed = True
            _run([*prefix, "daemon-reload"], check=False)
    return removed


def is_active_linux(backend: str, service_name: str = "evileye") -> bool:
    prefix = systemctl_prefix(backend)
    proc = _run([*prefix, "is-active", f"{service_name}.service"], check=False)
    return proc.stdout.strip() == "active"
