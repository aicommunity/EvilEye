#!/usr/bin/env python3
"""Install runtime dependencies declared by an installed package."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from importlib import metadata


def requirement_name(req: str) -> str:
    return re.split(r"[<>=!;\[]", req, maxsplit=1)[0].strip().lower()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", default="evileye")
    parser.add_argument(
        "--skip",
        default="torch,torchvision,torchaudio,ultralytics",
        help="comma-separated requirement names to skip",
    )
    args = parser.parse_args()

    reqs = list(metadata.requires(args.package) or [])
    skip = {x.strip().lower() for x in args.skip.split(",") if x.strip()}
    filtered = [r for r in reqs if requirement_name(r) not in skip]
    if not filtered:
        print("No runtime dependencies to install")
        return 0

    print("Installing filtered runtime dependencies:")
    for item in filtered:
        print(f"  {item}")
    cmd = [sys.executable, "-m", "pip", "install", "--no-cache-dir", *filtered]
    subprocess.check_call(cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
