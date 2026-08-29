"""Render systemd unit files for EvilEye web service."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


_SYSTEM_TEMPLATE = """\
[Unit]
Description=EvilEye Web Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={{WORKING_DIRECTORY}}
ExecStart={{EVILEYE_BIN}} server --host {{HOST}} --port {{PORT}} --no-reload{{CONFIG_ARGS}}{{SSL_ARGS}}
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
Environment=PYTHONUNBUFFERED=1
Environment=EVILEYE_SITE_DIR={{WORKING_DIRECTORY}}

[Install]
WantedBy=multi-user.target
"""

_USER_TEMPLATE = """\
[Unit]
Description=EvilEye Web Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={{WORKING_DIRECTORY}}
ExecStart={{EVILEYE_BIN}} server --host {{HOST}} --port {{PORT}} --no-reload{{CONFIG_ARGS}}{{SSL_ARGS}}
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
Environment=PYTHONUNBUFFERED=1
Environment=EVILEYE_SITE_DIR={{WORKING_DIRECTORY}}

[Install]
WantedBy=default.target
"""


def config_args(config: Optional[str]) -> str:
    if not config:
        return ""
    return f" --config {config}"


def ssl_args(ssl_certfile: Optional[str] = None, ssl_keyfile: Optional[str] = None) -> str:
    if not ssl_certfile or not ssl_keyfile:
        return ""
    return f" --ssl-certfile {ssl_certfile} --ssl-keyfile {ssl_keyfile}"


def _fill_placeholders(
    template: str,
    *,
    working_directory: str | Path,
    evileye_bin: str,
    host: str,
    port: int,
    config: Optional[str],
    ssl_certfile: Optional[str] = None,
    ssl_keyfile: Optional[str] = None,
) -> str:
    return (
        template.replace("{{WORKING_DIRECTORY}}", str(Path(working_directory).resolve()))
        .replace("{{EVILEYE_BIN}}", evileye_bin)
        .replace("{{HOST}}", host)
        .replace("{{PORT}}", str(port))
        .replace("{{CONFIG_ARGS}}", config_args(config))
        .replace("{{SSL_ARGS}}", ssl_args(ssl_certfile, ssl_keyfile))
    )


def render_unit(
    *,
    working_directory: str | Path,
    evileye_bin: str,
    host: str = "0.0.0.0",
    port: int = 8181,
    config: Optional[str] = None,
    user_mode: bool = True,
    ssl_certfile: Optional[str] = None,
    ssl_keyfile: Optional[str] = None,
) -> str:
    template = _USER_TEMPLATE if user_mode else _SYSTEM_TEMPLATE
    return _fill_placeholders(
        template,
        working_directory=working_directory,
        evileye_bin=evileye_bin,
        host=host,
        port=port,
        config=config,
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
    )


def load_template_from_package(user_mode: bool = True) -> Optional[str]:
    """Optional packaged .in template; fall back to embedded if missing."""
    candidates = [
        Path(__file__).resolve().parents[2] / "deploy" / "service" / "evileye.service.in",
        Path(__file__).resolve().parent / "templates" / "evileye.service.in",
    ]
    for path in candidates:
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            # Packaged template uses system WantedBy; adjust for user if needed.
            if user_mode and "WantedBy=multi-user.target" in text:
                text = text.replace("WantedBy=multi-user.target", "WantedBy=default.target")
            return text
    return None


def render_unit_prefer_file(
    *,
    working_directory: str | Path,
    evileye_bin: str,
    host: str = "0.0.0.0",
    port: int = 8181,
    config: Optional[str] = None,
    user_mode: bool = True,
    ssl_certfile: Optional[str] = None,
    ssl_keyfile: Optional[str] = None,
) -> str:
    packed = load_template_from_package(user_mode=user_mode)
    if packed is None or "{{SSL_ARGS}}" not in packed:
        return render_unit(
            working_directory=working_directory,
            evileye_bin=evileye_bin,
            host=host,
            port=port,
            config=config,
            user_mode=user_mode,
            ssl_certfile=ssl_certfile,
            ssl_keyfile=ssl_keyfile,
        )
    return _fill_placeholders(
        packed,
        working_directory=working_directory,
        evileye_bin=evileye_bin,
        host=host,
        port=port,
        config=config,
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
    )
