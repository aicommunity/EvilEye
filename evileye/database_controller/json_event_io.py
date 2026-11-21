"""Shared JSON append helpers for event metadata files."""

from __future__ import annotations

import json
import os
from typing import Any, List


def load_json_records(file_path: str) -> List[Any]:
    if not os.path.isfile(file_path):
        return []
    try:
        with open(file_path, encoding="utf-8") as f:
            return json.load(f) or []
    except Exception:
        return []


def append_json_record(file_path: str, record: dict) -> None:
    """Append one record to a JSON array file (create parent dirs if needed)."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    records = load_json_records(file_path)
    records.append(record)
    tmp_path = f"{file_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, file_path)
