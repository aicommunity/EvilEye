"""Helpers for events journal integration tests."""

from __future__ import annotations

import datetime
import json
import os
from typing import Any


def journal_today_folder(base_dir: str = "EvilEyeData") -> tuple[str, str]:
    today = datetime.date.today().strftime("%Y_%m_%d")
    test_date_dir = os.path.join(base_dir, today)
    os.makedirs(test_date_dir, exist_ok=True)
    return today, test_date_dir


def write_json(path: str, data: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


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
