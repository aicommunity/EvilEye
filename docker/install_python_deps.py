#!/usr/bin/env python3
"""Install EvilEye runtime deps without replacing CUDA torch / ultralytics from the base image."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib  # type: ignore

SKIP_NAMES = frozenset(
    {
        "ultralytics",
        "torch",
        "torchvision",
        "torchaudio",
    }
)


def requirement_name(req: str) -> str:
    return re.split(r"[<>=!;\[]", req, maxsplit=1)[0].strip().lower()


def main() -> int:
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    reqs = list(data["project"]["dependencies"])
    filtered = [r for r in reqs if requirement_name(r) not in SKIP_NAMES]
    print("Installing filtered deps:")
    for item in filtered:
        print(f"  {item}")
    cmd = [sys.executable, "-m", "pip", "install", "--no-cache-dir", *filtered]
    subprocess.check_call(cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
