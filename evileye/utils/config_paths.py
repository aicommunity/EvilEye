"""Lightweight config path helpers (no ML / DB imports)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Union


def normalize_config_path(config_path: Union[str, Path]) -> str:
    """Normalize configuration file path by adding ``configs/`` prefix when needed."""
    config_path_str = str(config_path)

    if os.path.isabs(config_path_str) or config_path_str.startswith("configs"):
        return config_path_str

    return os.path.join("configs", config_path_str)
