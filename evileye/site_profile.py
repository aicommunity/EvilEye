"""Site production profile stored in `.evileye_service.json`."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from evileye.service_manager.state import load_state, save_state


def load_profile(site_dir: Path | None = None) -> dict[str, Any]:
    return dict(load_state(site_dir))


def save_profile(updates: dict[str, Any], site_dir: Path | None = None) -> dict[str, Any]:
    current = load_profile(site_dir)
    current.update(updates)
    if "version" not in current:
        current["version"] = 2
    save_state(current, site_dir)
    return current


def resolve_production_config(site_dir: Path | None = None) -> Optional[str]:
    profile = load_profile(site_dir)
    for key in ("production_config", "config", "watchdog_config"):
        value = profile.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def resolve_watchdog_config(site_dir: Path | None = None) -> Optional[str]:
    profile = load_profile(site_dir)
    for key in ("watchdog_config", "production_config", "config"):
        value = profile.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def pipeline_launch_mode(site_dir: Path | None = None) -> str:
    profile = load_profile(site_dir)
    mode = str(profile.get("pipeline_launch") or "auto").strip().lower()
    if mode in {"auto", "managed", "direct"}:
        return mode
    return "auto"


def service_port(site_dir: Path | None = None, default: int = 8181) -> int:
    profile = load_profile(site_dir)
    try:
        return int(profile.get("port") or default)
    except (TypeError, ValueError):
        return default


def gui_default(site_dir: Path | None = None) -> bool:
    profile = load_profile(site_dir)
    return bool(profile.get("gui_default", False))
