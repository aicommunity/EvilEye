#!/usr/bin/env python3
"""Validate all JSON files under configs/. Used by pre-commit local hook."""
import json
import sys
from pathlib import Path


def main() -> int:
    errors = []
    configs_dir = Path(__file__).resolve().parent.parent / "configs"
    if not configs_dir.is_dir():
        print("configs/ not found", file=sys.stderr)
        return 1
    for config_file in sorted(configs_dir.glob("*.json")):
        try:
            with open(config_file, encoding="utf-8") as f:
                json.load(f)
        except Exception as e:
            errors.append(f"{config_file}: {e}")
    if errors:
        print("JSON validation errors:")
        for error in errors:
            print(f"  {error}")
        return 1
    print("All JSON configs are valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
