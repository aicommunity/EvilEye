"""Cross-platform EvilEye OS service install/uninstall."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from evileye.service_manager import linux as linux_backend
from evileye.service_manager import windows as windows_backend
from evileye.service_manager.minimal_config import ensure_system_config
from evileye.service_manager.state import (
    SERVICE_NAME,
    clear_state,
    load_state,
    resolve_evileye_bin,
    save_state,
)
from evileye.service_manager.unit_render import render_unit_prefer_file


@dataclass
class ServiceActionResult:
    ok: bool
    message: str
    state: dict[str, Any]
    unit_text: Optional[str] = None
    dry_run: bool = False
    warn_only: bool = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_config_rel(config: Optional[str], site_dir: Path) -> Optional[str]:
    if not config:
        return None
    from evileye.utils.utils import normalize_config_path

    normalized = Path(normalize_config_path(config))
    if not normalized.is_absolute():
        normalized = (site_dir / normalized).resolve()
    else:
        normalized = normalized.resolve()
    try:
        rel = normalized.relative_to(site_dir.resolve())
        return str(rel).replace("\\", "/")
    except ValueError:
        return str(normalized)


def service_status(site_dir: Path | None = None) -> dict[str, Any]:
    root = Path(site_dir) if site_dir is not None else Path.cwd()
    state = load_state(root)
    out = dict(state) if state else {"installed": False}
    out["site_dir"] = str(root.resolve())
    return out


def install_service(
    *,
    site_dir: Path | None = None,
    config: Optional[str] = None,
    host: str = "0.0.0.0",
    port: int = 8181,
    force_user: bool = False,
    force_system: bool = False,
    dry_run: bool = False,
    ensure_minimal_config: bool = True,
) -> ServiceActionResult:
    root = (Path(site_dir) if site_dir is not None else Path.cwd()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "configs").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)

    if ensure_minimal_config:
        ensure_system_config(root)

    config_rel = _normalize_config_rel(config, root)
    evileye_bin = resolve_evileye_bin()

    if sys.platform.startswith("linux"):
        backend = linux_backend.resolve_mode(force_user=force_user, force_system=force_system)
        user_mode = backend == "systemd-user"
        unit_text = render_unit_prefer_file(
            working_directory=root,
            evileye_bin=evileye_bin,
            host=host,
            port=port,
            config=config_rel,
            user_mode=user_mode,
        )
        result = linux_backend.install_linux(
            unit_text=unit_text,
            backend=backend,
            service_name=SERVICE_NAME,
            dry_run=dry_run,
        )
        state = {
            "version": 1,
            "installed": True,
            "backend": backend,
            "service_name": SERVICE_NAME,
            "unit_path": str(result.unit_path),
            "working_directory": str(root),
            "python_executable": sys.executable,
            "evileye_executable": evileye_bin,
            "host": host,
            "port": port,
            "config": config_rel,
            "installed_at": _utc_now(),
        }
        if not dry_run:
            save_state(state, root)
        url = f"http://{host if host != '0.0.0.0' else '127.0.0.1'}:{port}"
        return ServiceActionResult(
            ok=True,
            message=(
                f"Service installed ({backend}): {result.unit_path}\n"
                f"Web UI: {url}\n"
                "Change the bootstrap admin password on first login."
            ),
            state=state,
            unit_text=unit_text,
            dry_run=dry_run,
        )

    if sys.platform.startswith("win"):
        try:
            win = windows_backend.install_windows(
                site_dir=root,
                host=host,
                port=port,
                config=config_rel,
                dry_run=dry_run,
            )
        except windows_backend.WindowsServiceError as exc:
            # Still write launcher script for manual start when possible
            ensure_system_config(root)
            return ServiceActionResult(
                ok=False,
                message=str(exc),
                state={},
                dry_run=dry_run,
                warn_only=True,
            )
        state = {
            "version": 1,
            "installed": True,
            "backend": win.backend,
            "service_name": win.service_name,
            "unit_path": str(win.unit_path),
            "working_directory": str(root),
            "python_executable": sys.executable,
            "evileye_executable": evileye_bin,
            "host": host,
            "port": port,
            "config": config_rel,
            "installed_at": _utc_now(),
        }
        if not dry_run:
            save_state(state, root)
        url = f"http://127.0.0.1:{port}"
        return ServiceActionResult(
            ok=True,
            message=f"Service installed ({win.backend}). Web UI: {url}",
            state=state,
            dry_run=dry_run,
        )

    return ServiceActionResult(
        ok=False,
        message=f"Unsupported platform for OS service: {sys.platform}",
        state={},
        warn_only=True,
    )


def ensure_service(
    *,
    site_dir: Path | None = None,
    config: Optional[str] = None,
    host: str = "0.0.0.0",
    port: int = 8181,
    force_user: bool = False,
    force_system: bool = False,
    dry_run: bool = False,
) -> ServiceActionResult:
    """Idempotent install/update used by `evileye deploy`."""
    return install_service(
        site_dir=site_dir,
        config=config,
        host=host,
        port=port,
        force_user=force_user,
        force_system=force_system,
        dry_run=dry_run,
        ensure_minimal_config=True,
    )


def uninstall_service(
    *,
    site_dir: Path | None = None,
    dry_run: bool = False,
) -> ServiceActionResult:
    root = (Path(site_dir) if site_dir is not None else Path.cwd()).resolve()
    state = load_state(root)

    if sys.platform.startswith("linux"):
        backend = state.get("backend") if isinstance(state.get("backend"), str) else None
        unit_path = state.get("unit_path")
        removed = linux_backend.uninstall_linux(
            backend=backend,
            unit_path=unit_path,
            service_name=str(state.get("service_name") or SERVICE_NAME),
            dry_run=dry_run,
        )
        if not state and not removed:
            return ServiceActionResult(
                ok=True,
                message="EvilEye service is not installed.",
                state={},
                dry_run=dry_run,
            )
        if not dry_run:
            clear_state(root)
        return ServiceActionResult(
            ok=True,
            message="EvilEye service uninstalled." if removed or state else "EvilEye service is not installed.",
            state={},
            dry_run=dry_run,
        )

    if sys.platform.startswith("win"):
        removed = windows_backend.uninstall_windows(
            site_dir=root,
            service_name=str(state.get("service_name") or "EvilEye"),
            dry_run=dry_run,
        )
        if not dry_run:
            clear_state(root)
        if not removed and not state:
            return ServiceActionResult(
                ok=True,
                message="EvilEye service is not installed.",
                state={},
                dry_run=dry_run,
            )
        return ServiceActionResult(
            ok=True,
            message="EvilEye service uninstalled.",
            state={},
            dry_run=dry_run,
        )

    if not state:
        return ServiceActionResult(
            ok=True,
            message="EvilEye service is not installed.",
            state={},
            dry_run=dry_run,
        )
    if not dry_run:
        clear_state(root)
    return ServiceActionResult(
        ok=True,
        message="Cleared local service state (platform has no service backend).",
        state={},
        dry_run=dry_run,
    )
