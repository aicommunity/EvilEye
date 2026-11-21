#!/usr/bin/env python3
"""Dump main-process memory attribution via control IPC or /ready HTTP.

Usage:
  python scripts/dump_main_memory_attrs.py
  python scripts/dump_main_memory_attrs.py --url http://127.0.0.1:8181/ready
"""

from __future__ import annotations

import argparse
import json
import sys


def _via_ipc() -> dict:
    from evileye.api.core.control_ipc import control_socket_path, send_control_command

    path = control_socket_path()
    if not path.exists():
        raise RuntimeError(f"control socket missing: {path}")
    resp = send_control_command({"cmd": "get_memory_attribution"}, timeout=2.0)
    if not isinstance(resp, dict) or not resp.get("ok"):
        raise RuntimeError(f"IPC failed: {resp}")
    return resp.get("stats") or {}


def _via_http(url: str) -> dict:
    import urllib.request

    with urllib.request.urlopen(url, timeout=5) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    attrs = payload.get("memory_attribution")
    if not isinstance(attrs, dict):
        raise RuntimeError("memory_attribution missing from /ready (pipeline may be old)")
    return attrs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="", help="Optional /ready URL (fallback to IPC)")
    parser.add_argument("--json", action="store_true", help="Print raw JSON only")
    args = parser.parse_args()

    err = None
    attrs = None
    try:
        attrs = _via_ipc()
    except Exception as exc:
        err = exc
        if args.url:
            attrs = _via_http(args.url)
        else:
            try:
                attrs = _via_http("http://127.0.0.1:8181/ready")
            except Exception as exc2:
                print(f"IPC failed: {err}; HTTP failed: {exc2}", file=sys.stderr)
                return 1

    if args.json:
        print(json.dumps(attrs, indent=2, ensure_ascii=False, default=str))
        return 0

    from evileye.utils.memory_attribution import format_memory_attribution_line

    print(format_memory_attribution_line(attrs))
    print(json.dumps(attrs, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
