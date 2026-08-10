"""Generate minimal configs/system.json for post-install Web setup."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def minimal_system_config() -> dict[str, Any]:
    """Return a scaffold config without sources/analytics/DB credentials."""
    return {
        "pipeline": {
            "pipeline_class": "PipelineSurveillance",
            "sources": [],
            "detectors": [],
            "trackers": [],
            "mc_trackers": [],
        },
        "controller": {
            "fps": 30,
            "use_database": False,
            "gui_enabled": False,
            "show_main_gui": False,
            "show_journal": False,
            "enable_close_from_gui": False,
            "auto_restart": False,
        },
        "database": {
            "image_dir": "",
            "preview_width": 300,
            "preview_height": 150,
        },
        "record": {
            "enabled": False,
            "continuous_recording_enabled": False,
            "event_recording_enabled": False,
        },
        "server": {
            "enabled": True,
            "host": "0.0.0.0",
            "port": 8181,
            "execution_mode": "process",
        },
        "objects_handler": {},
        "events_detectors": {},
        "events_processor": {},
        "visualizer": {"num_width": 1, "num_height": 1},
        "storage_monitor": {},
    }


def ensure_system_config(site_dir: Path | None = None, force: bool = False) -> Path:
    """Create configs/system.json if missing (or force overwrite)."""
    root = Path(site_dir) if site_dir is not None else Path.cwd()
    configs = root / "configs"
    configs.mkdir(parents=True, exist_ok=True)
    path = configs / "system.json"
    if path.exists() and not force:
        return path
    path.write_text(json.dumps(minimal_system_config(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
