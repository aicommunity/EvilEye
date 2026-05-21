"""Helpers for events journal integration tests."""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Any

import pytest

EXPECTED_JOURNAL_HEADERS = [
    "Time",
    "Event",
    "Information",
    "Source",
    "Time lost",
    "Preview",
    "Lost preview",
]


def journal_today_folder(base_dir: str = "EvilEyeData") -> tuple[str, str]:
    today = datetime.date.today().strftime("%Y_%m_%d")
    test_date_dir = os.path.join(base_dir, today)
    os.makedirs(test_date_dir, exist_ok=True)
    return today, test_date_dir


def write_json(path: str, data: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_db_config() -> dict[str, Any]:
    """Load database configuration from project tree."""
    current = Path(__file__).resolve()
    project_root = None
    for parent in current.parents:
        if parent.name == "EvilEye":
            project_root = parent
            break
    if project_root is None:
        project_root = current.parents[4]

    for rel in ("evileye/database_config.json", "database_config.json"):
        cfg_path = project_root / rel
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                return json.load(f)

    pytest.skip(
        "database_config.json not found under project root "
        f"({project_root})"
    )


def table_horizontal_headers(table) -> list[str]:
    headers = []
    for i in range(table.columnCount()):
        item = table.horizontalHeaderItem(i)
        headers.append(item.text() if item else "")
    return headers


def journal_actions_available(db_journal_win, deferred_journal_creation) -> bool:
    """Mirror MainWindow._configure_journal_button availability logic."""
    if db_journal_win is not None:
        return True
    if not deferred_journal_creation:
        return False
    if isinstance(deferred_journal_creation, dict):
        return bool(
            deferred_journal_creation.get("enabled", False)
            and not deferred_journal_creation.get("created", False)
        )
    return False
