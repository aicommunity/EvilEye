"""Detached worker for editable plugin installation and optional service restart."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from evileye.core.extension_builder import _install_and_restart


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operation", required=True)
    parser.add_argument("--site", required=True)
    args = parser.parse_args()
    root = Path(args.site).resolve()
    os.environ["EVILEYE_SITE_DIR"] = str(root)
    _install_and_restart(args.operation, root)


if __name__ == "__main__":
    main()
