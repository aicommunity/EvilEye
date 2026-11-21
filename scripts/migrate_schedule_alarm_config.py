#!/usr/bin/env python3
"""Migrate FieldOfViewEventsDetector configs to ScheduleAlarmEventsDetector."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evileye.core.paths import configs_dir
from evileye.events_detectors.schedule_alarm_logic import (
    DETECTOR_CONFIG_KEY,
    LEGACY_DETECTOR_CONFIG_KEY,
    normalize_schedule_dict,
    schedule_to_json,
)


REPO_ROOT = Path(__file__).resolve().parents[1]

TARGET_DIRS = [
    configs_dir(),
    REPO_ROOT / "evileye" / "samples_configs",
    REPO_ROOT / "tests" / "data" / "configs",
    REPO_ROOT / "evileye" / "visualization_modules" / "configurer",
    REPO_ROOT / "evileye" / "configs",
]


def _migrate_sources(sources: dict) -> dict:
    out: dict = {}
    if not isinstance(sources, dict):
        return out
    for key, value in sources.items():
        schedule = normalize_schedule_dict(value, default_enabled=True)
        out[str(key)] = schedule_to_json(schedule)
    return out


def migrate_config_obj(data: dict) -> tuple[dict, list[str]]:
    changes: list[str] = []
    if not isinstance(data, dict):
        return data, changes

    events = data.get("events_detectors")
    if isinstance(events, dict) and LEGACY_DETECTOR_CONFIG_KEY in events:
        legacy = events.pop(LEGACY_DETECTOR_CONFIG_KEY)
        if DETECTOR_CONFIG_KEY not in events:
            events[DETECTOR_CONFIG_KEY] = legacy
            changes.append("renamed events_detectors key")

    section = events.get(DETECTOR_CONFIG_KEY) if isinstance(events, dict) else None
    if isinstance(section, dict):
        sources = section.get("sources")
        if isinstance(sources, dict):
            migrated = _migrate_sources(sources)
            if migrated != sources:
                section["sources"] = migrated
                changes.append("normalized schedule sources")
        if "default_schedule" not in section:
            section["default_schedule"] = schedule_to_json(
                normalize_schedule_dict(None, default_enabled=False)
            )
            changes.append("added default_schedule")

    adapters = data.get("database_adapters")
    if isinstance(adapters, dict) and "DatabaseAdapterFieldOfViewEvents" in adapters:
        legacy_adapter = adapters.pop("DatabaseAdapterFieldOfViewEvents")
        if "DatabaseAdapterScheduleAlarmEvents" not in adapters:
            if isinstance(legacy_adapter, dict):
                legacy_adapter = dict(legacy_adapter)
                if legacy_adapter.get("table_name") == "fov_events":
                    legacy_adapter["table_name"] = "schedule_alarm_events"
                if legacy_adapter.get("event_name") == "FieldOfViewEvent":
                    legacy_adapter["event_name"] = "ScheduleAlarmEvent"
            adapters["DatabaseAdapterScheduleAlarmEvents"] = legacy_adapter
            changes.append("renamed database adapter key")

    database = data.get("database")
    if isinstance(database, dict):
        tables = database.get("tables")
        if isinstance(tables, dict) and "fov_events" in tables and "schedule_alarm_events" not in tables:
            tables["schedule_alarm_events"] = tables.pop("fov_events")
            changes.append("renamed database.tables key")

    return data, changes


def iter_config_files() -> list[Path]:
    files: list[Path] = []
    for root in TARGET_DIRS:
        if not root.exists():
            continue
        files.extend(sorted(root.rglob("*.json")))
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and not args.write:
        parser.error("Specify --dry-run or --write")

    changed = 0
    for path in iter_config_files():
        if "reports" in path.parts:
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception:
            continue
        migrated, changes = migrate_config_obj(data)
        if not changes:
            continue
        changed += 1
        print(f"{path}: {', '.join(changes)}")
        if args.write:
            path.write_text(json.dumps(migrated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Done. files_changed={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
