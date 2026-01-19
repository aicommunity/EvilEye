import json
from pathlib import Path


SCHEDULED_RESTART_DEFAULTS = {
    "enabled": False,
    "mode": "daily_time",
    "time": "01:00",
    "interval_minutes": 0,
}


def update_config(path: Path) -> bool:
    """Add controller.scheduled_restart section to config JSON if missing."""
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except Exception:
        return False

    if not isinstance(data, dict):
        return False

    controller = data.setdefault("controller", {})
    if not isinstance(controller, dict):
        # Do not touch configs with unexpected structure
        return False

    sched = controller.get("scheduled_restart")
    changed = False

    if not isinstance(sched, dict):
        controller["scheduled_restart"] = dict(SCHEDULED_RESTART_DEFAULTS)
        changed = True
    else:
        # Ensure all keys present with defaults, but do not enable feature implicitly
        for key, default_value in SCHEDULED_RESTART_DEFAULTS.items():
            if key not in sched:
                sched[key] = default_value
                changed = True
        # Explicitly ensure enabled is False by default if not already True
        if sched.get("enabled") is None:
            sched["enabled"] = False

    if changed:
        path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    return changed


def main() -> None:
    root = Path(__file__).parent.parent
    targets = [
        root / "configs",
        root / "evileye" / "samples_configs",
    ]

    updated_files = []

    for folder in targets:
        if not folder.exists():
            continue
        for cfg_path in folder.glob("*.json"):
            if update_config(cfg_path):
                updated_files.append(cfg_path.relative_to(root))

    if updated_files:
        print("Updated configs with scheduled_restart:")
        for p in updated_files:
            print(f"  - {p}")
    else:
        print("No configs were updated (all already had scheduled_restart).")


if __name__ == "__main__":
    main()

