"""Persist install state for EvilEye OS service (.evileye_service.json)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

STATE_FILENAME = ".evileye_service.json"
SERVICE_NAME = "evileye"


def state_path(site_dir: Path | None = None) -> Path:
    root = Path(site_dir) if site_dir is not None else Path.cwd()
    return root / STATE_FILENAME


def load_state(site_dir: Path | None = None) -> dict[str, Any]:
    path = state_path(site_dir)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_state(payload: dict[str, Any], site_dir: Path | None = None) -> Path:
    path = state_path(site_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return path


def clear_state(site_dir: Path | None = None) -> bool:
    path = state_path(site_dir)
    if not path.exists():
        return False
    path.unlink()
    return True


def is_installed(site_dir: Path | None = None) -> bool:
    state = load_state(site_dir)
    return bool(state.get("installed"))


def resolve_evileye_bin() -> str:
    """Prefer installed console script; fall back to python -m wrapper."""
    import shutil
    import sys

    found = shutil.which("evileye")
    if found:
        return found
    return f"{sys.executable} -m evileye.cli_wrapper"
