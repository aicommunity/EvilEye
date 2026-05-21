"""Atomic JSON load/save helpers."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Union


def load_json(path: Union[str, Path]) -> Dict[str, Any]:
    """Load JSON object from a file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json_atomic(path: Union[str, Path], data: Dict[str, Any]) -> bool:
    """Write JSON atomically via a temporary file and os.replace."""
    file_path = str(path)
    if not file_path:
        return False
    dir_name = os.path.dirname(file_path) or "."
    try:
        with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", delete=False, dir=dir_name, prefix=".tmp_"
        ) as tf:
            json.dump(data, tf, indent=4, ensure_ascii=False)
            temp_path = tf.name
        os.replace(temp_path, file_path)
        return True
    except OSError:
        return False
