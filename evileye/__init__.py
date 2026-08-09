"""
EvilEye - Intelligence video surveillance system

A comprehensive video surveillance system with object detection, tracking,
and multi-camera support.
"""

from __future__ import annotations

from pathlib import Path


def _version_from_pyproject() -> str:
    """Read [project].version from the repo pyproject.toml (dev / editable tree)."""
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return "0.0.0"
    in_project = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_project = line == "[project]"
            continue
        if not in_project:
            continue
        if line.startswith("version") and "=" in line:
            _, _, rest = line.partition("=")
            return rest.strip().strip('"').strip("'")
    return "0.0.0"


def _resolve_version() -> str:
    # Installed package metadata (matches pyproject when built/installed).
    try:
        from importlib.metadata import version as pkg_version

        return pkg_version("evileye")
    except Exception:
        pass
    return _version_from_pyproject()


# Kept for compatibility: `from evileye import __version__` — value always tracks pyproject.
__version__ = _resolve_version()
__author__ = "AI Community"
__email__ = "palexab@gmail.com"

# Лёгкий __init__: без настройки логирования, без тяжёлых импортов, без subprocess при импорте
# Тяжёлые компоненты инициализируются по месту использования

__all__ = [
    "__version__",
]
