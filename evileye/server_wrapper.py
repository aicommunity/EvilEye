#!/usr/bin/env python3
"""
Wrapper for EvilEye API server that ensures proper path setup and stable entry point
"""
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
if project_root.exists():
    sys.path.insert(0, str(project_root))

from evileye.server import main


def main_wrapper() -> int:
    main()
    return 0


def run() -> None:
    sys.exit(main_wrapper())


def start() -> None:
    sys.exit(main_wrapper())


def cli() -> None:
    sys.exit(main_wrapper())


if __name__ == '__main__':
    sys.exit(main_wrapper())
