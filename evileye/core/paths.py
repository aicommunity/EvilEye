"""Cross-platform site / data / runtime path helpers for EvilEye."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

_SITE_ENV = "EVILEYE_SITE_DIR"
_DATA_ENV = "EVILEYE_DATA_DIR"


def site_root(explicit: Optional[Path | str] = None) -> Path:
    """Resolve the EvilEye site directory.

    Preference: ``explicit`` → ``EVILEYE_SITE_DIR`` → ``Path.cwd()``.
    """
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    env = (os.environ.get(_SITE_ENV) or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()


def creds_path(root: Optional[Path | str] = None) -> Path:
    return site_root(root) / "credentials.json"


def configs_dir(root: Optional[Path | str] = None) -> Path:
    return site_root(root) / "configs"


def logs_dir(root: Optional[Path | str] = None) -> Path:
    return site_root(root) / "logs"


def monitor_dir(root: Optional[Path | str] = None) -> Path:
    return site_root(root) / "monitor"


def data_dir(
    preferred: Optional[str] = None,
    *,
    root: Optional[Path | str] = None,
    fallback: str = "EvilEyeData",
) -> Path:
    """Resolve writable image/data directory (wraps database_config_utils when available)."""
    try:
        from evileye.utils.database_config_utils import resolve_writable_image_dir

        chosen = resolve_writable_image_dir(preferred, fallback=fallback, env_var=_DATA_ENV)
        path = Path(chosen)
        if not path.is_absolute():
            path = site_root(root) / path
        return path.resolve()
    except Exception:
        env = (os.environ.get(_DATA_ENV) or "").strip()
        raw = preferred or env or fallback
        path = Path(raw)
        if not path.is_absolute():
            path = site_root(root) / path
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()


def runtime_dir() -> Path:
    """Process-local runtime state (mp sessions, locks). Never uses Unix ``/tmp`` hardcoded."""
    xdg = (os.environ.get("XDG_RUNTIME_DIR") or "").strip()
    if xdg:
        base = Path(xdg)
    else:
        base = Path(tempfile.gettempdir())
    path = base / "evileye"
    path.mkdir(parents=True, exist_ok=True)
    return path


def as_config_posix(path: Path | str) -> str:
    """Serialize a path for JSON configs using forward slashes."""
    return Path(path).as_posix()
