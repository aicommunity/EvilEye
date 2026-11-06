"""Lightweight config path helpers (no ML / DB imports)."""

from __future__ import annotations

import os
from pathlib import Path
from pathlib import PurePosixPath
from typing import Union


def normalize_config_path(config_path: Union[str, Path]) -> str:
    """Normalize configuration file path by adding ``configs/`` prefix when needed."""
    config_path_str = str(config_path).replace("\\", "/")

    if os.path.isabs(config_path_str) or config_path_str.startswith("configs"):
        return config_path_str

    return PurePosixPath("configs", config_path_str).as_posix()
