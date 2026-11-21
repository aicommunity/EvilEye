"""Cross-platform EvilEye OS service install/uninstall."""

from __future__ import annotations

import json
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


def _resolve_service_ssl(
    root: Path,
    *,
    ssl_certfile: Optional[str] = None,
    ssl_keyfile: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    from evileye.api.core.ssl_files import resolve_ssl_files

    cert, key = resolve_ssl_files(cli_cert=ssl_certfile, cli_key=ssl_keyfile, site_dir=root)
    return (str(cert) if cert else None, str(key) if key else None)


def _web_ui_url(host: str, port: int, *, tls: bool) -> str:
    display_host = host if host not in {"0.0.0.0", "::", "[::]"} else "127.0.0.1"
    scheme = "https" if tls else "http"
    return f"{scheme}://{display_host}:{port}"


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
    from evileye.utils.config_paths import normalize_config_path

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
    from evileye.core.paths import site_root

    root = Path(site_dir).resolve() if site_dir is not None else site_root()
    state = load_state(root)
    out = dict(state) if state else {"installed": False}
    out["site_dir"] = str(root.resolve())
    return out


def is_web_os_service_enabled() -> bool:
    """True when systemd unit evileye.service is enabled (user or system)."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        return linux_backend.is_enabled_linux("systemd-user") or linux_backend.is_enabled_linux(
            "systemd-system"
        )
    except Exception:
        return False


def is_web_os_service_active() -> bool:
    """True when systemd unit evileye.service is running (user or system)."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        return linux_backend.is_active_linux("systemd-user") or linux_backend.is_active_linux(
            "systemd-system"
        )
    except Exception:
        return False


def web_service_main_pid(service_name: str = "evileye") -> Optional[int]:
    """MainPID of the installed OS web service, if running."""
    if not sys.platform.startswith("linux"):
        return None
    try:
        for backend in ("systemd-user", "systemd-system"):
            pid = linux_backend.main_pid_linux(backend, service_name=service_name)
            if pid:
                return pid
    except Exception:
        return None
    return None


def probe_port_scheme(port: int, host: str = "127.0.0.1") -> str:
    """Return 'https', 'http', or 'closed'."""
    return _probe_port_scheme(port, host=host)


def is_service_installed(site_dir: Path | None = None) -> bool:
    from evileye.core.paths import site_root

    root = Path(site_dir).resolve() if site_dir is not None else site_root()
    state = load_state(root)
    return bool(state.get("installed"))


def _resolve_service_backend(state: dict[str, Any]) -> Optional[str]:
    backend = state.get("backend")
    if isinstance(backend, str) and backend:
        return backend
    if sys.platform.startswith("linux"):
        if linux_backend.is_enabled_linux("systemd-user"):
            return "systemd-user"
        if linux_backend.is_enabled_linux("systemd-system"):
            return "systemd-system"
    if sys.platform.startswith("win"):
        return "windows-task"
    return None


def control_service(action: str, *, site_dir: Path | None = None) -> ServiceActionResult:
    """Start/stop/restart/status the installed OS web service."""
    from evileye.core.paths import site_root

    root = Path(site_dir).resolve() if site_dir is not None else site_root()
    state = load_state(root)
    if not state.get("installed"):
        return ServiceActionResult(ok=False, message="EvilEye OS web service is not installed.", state=state)

    service_name = str(state.get("service_name") or SERVICE_NAME)
    backend = _resolve_service_backend(state)
    action_norm = action.strip().lower()
    if action_norm not in {"start", "stop", "restart", "status"}:
        return ServiceActionResult(ok=False, message=f"Unknown service action: {action}", state=state)

    if sys.platform.startswith("linux"):
        if not backend:
            backend = "systemd-user"
        try:
            result = linux_backend.control_linux_service(backend, action_norm, service_name=service_name)
        except linux_backend.ServiceManagerError as exc:
            return ServiceActionResult(ok=False, message=str(exc), state=state)
        ok = result.returncode == 0 or action_norm == "status"
        message = (result.stdout or result.stderr or "").strip() or f"systemctl {action_norm} exit {result.returncode}"
        if action_norm in {"start", "restart"} and ok:
            port = int(state.get("port") or 8181)
            scheme = probe_port_scheme(port)
            message = f"Service {action_norm} OK (port {port}: {scheme})"
        return ServiceActionResult(ok=ok, message=message, state=state)

    if sys.platform.startswith("win"):
        try:
            result = windows_backend.control_windows_service(
                action_norm,
                service_name=str(state.get("service_name") or "EvilEye"),
            )
        except windows_backend.WindowsServiceError as exc:
            return ServiceActionResult(ok=False, message=str(exc), state=state)
        return ServiceActionResult(ok=result.ok, message=result.message, state=state)

    return ServiceActionResult(ok=False, message=f"Unsupported platform: {sys.platform}", state=state)


def _probe_port_scheme(port: int, host: str = "127.0.0.1") -> str:
    """Return 'https', 'http', or 'closed'."""
    import socket
    import ssl

    try:
        raw = socket.create_connection((host, port), timeout=1.5)
    except OSError:
        return "closed"
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            with ctx.wrap_socket(raw, server_hostname=host) as tls:
                tls.do_handshake()
                return "https"
        except ssl.SSLError:
            return "http"
    finally:
        try:
            raw.close()
        except OSError:
            pass


def _has_existing_web_users(root: Path) -> bool:
    creds = root / "credentials.json"
    if not creds.is_file():
        return False
    try:
        payload = json.loads(creds.read_text(encoding="utf-8"))
    except Exception:
        return False
    web_auth = payload.get("web_auth") if isinstance(payload, dict) else None
    users = web_auth.get("users") if isinstance(web_auth, dict) else None
    return isinstance(users, list) and bool(users)


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
    ssl_certfile: Optional[str] = None,
    ssl_keyfile: Optional[str] = None,
) -> ServiceActionResult:
    from evileye.api.core.ssl_files import SslConfigError
    from evileye.core.paths import site_root

    root = Path(site_dir).resolve() if site_dir is not None else site_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / "configs").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)

    if ensure_minimal_config:
        ensure_system_config(root)

    config_rel = _normalize_config_rel(config, root)
    evileye_bin = resolve_evileye_bin()
    try:
        cert_path, key_path = _resolve_service_ssl(root, ssl_certfile=ssl_certfile, ssl_keyfile=ssl_keyfile)
    except SslConfigError as exc:
        return ServiceActionResult(ok=False, message=str(exc), state={})
    tls = bool(cert_path and key_path)

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
            ssl_certfile=cert_path,
            ssl_keyfile=key_path,
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
            "ssl_certfile": cert_path,
            "installed_at": _utc_now(),
        }
        if not dry_run:
            save_state(state, root)
        url = _web_ui_url(host, port, tls=tls)
        notes = [
            f"Service installed ({backend}): {result.unit_path}",
            f"Web UI: {url}",
        ]
        if backend == "systemd-user" and not dry_run:
            linger_hint = getattr(result, "start_error", "") or ""
            if linger_hint.startswith("could not enable linger") or linger_hint.startswith(
                "loginctl not found"
            ):
                notes.append(
                    "User linger is off: after reboot the Web UI will not start until login. "
                    f"Fix: loginctl enable-linger $USER ({linger_hint})"
                )
            else:
                notes.append(
                    "User linger enabled (or already on): user unit starts at boot without GUI login."
                )
        if not dry_run and not getattr(result, "start_ok", True):
            scheme = _probe_port_scheme(port)
            notes.append(
                "The OS service did not start (port busy or systemd error). "
                "ERR_SSL_PROTOCOL_ERROR means the browser used HTTPS against a process still speaking HTTP "
                "(usually `evileye run` started before TLS). Restart that runtime from this site dir "
                "or stop it, then: systemctl --user restart evileye"
            )
            if scheme == "http":
                notes.append(f"Port {port} currently answers HTTP, not TLS.")
            elif result.start_error:
                notes.append(result.start_error.split("\n")[0][:300])
            return ServiceActionResult(
                ok=False,
                message="\n".join(notes),
                state=state,
                unit_text=unit_text,
                dry_run=dry_run,
                warn_only=True,
            )
        if not dry_run and tls:
            scheme = _probe_port_scheme(port)
            if scheme == "http":
                notes.append(
                    f"Port {port} still speaks HTTP. Restart `evileye run` so it loads certs from "
                    "configs/system.json, or stop it so this TLS service can bind."
                )
        if not _has_existing_web_users(root):
            notes.append("Change the bootstrap admin password on first login.")
        return ServiceActionResult(
            ok=True,
            message="\n".join(notes),
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
                ssl_certfile=cert_path,
                ssl_keyfile=key_path,
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
            "ssl_certfile": cert_path,
            "installed_at": _utc_now(),
        }
        if not dry_run:
            save_state(state, root)
        url = _web_ui_url("127.0.0.1", port, tls=tls)
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
    """Idempotent install/update used by `evileye service install`."""
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
    from evileye.core.paths import site_root

    root = Path(site_dir).resolve() if site_dir is not None else site_root()
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
