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


def apply_replacements(req: str, replacements: dict[str, str]) -> str:
    name = requirement_name(req)
    if name not in replacements:
        return req
    # Drop environment markers from the original req; replacement is explicit.
    return replacements[name]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", default="evileye")
    parser.add_argument(
        "--skip",
        default="torch,torchvision,torchaudio,ultralytics",
        help="comma-separated requirement names to skip",
    )
    parser.add_argument(
        "--replace",
        default="",
        help="comma-separated name=replacement (e.g. onnxruntime-gpu=onnxruntime)",
    )
    args = parser.parse_args()

    reqs = list(metadata.requires(args.package) or [])
    skip = {x.strip().lower() for x in args.skip.split(",") if x.strip()}
    replacements: dict[str, str] = {}
    for item in args.replace.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise SystemExit(f"invalid --replace entry: {item!r} (expected name=pkg)")
        src, dst = item.split("=", 1)
        replacements[src.strip().lower()] = dst.strip()

    filtered: list[str] = []
    for req in reqs:
        name = requirement_name(req)
        if name in skip and name not in replacements:
            continue
        if name in replacements:
            filtered.append(replacements[name])
            continue
        if name in skip:
            continue
        filtered.append(req)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for item in filtered:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    if not unique:
        print("No runtime dependencies to install")
        return 0

    print("Installing filtered runtime dependencies:")
    for item in unique:
        print(f"  {item}")
    cmd = [sys.executable, "-m", "pip", "install", "--no-cache-dir", *unique]
    subprocess.check_call(cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
