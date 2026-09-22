#!/usr/bin/env python3
"""Merge Playwright JSON + diagnose_playback_wan JSON into markdown report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(path: str) -> dict:
    p = Path(path)
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", default="", help="diagnose_playback_wan.json")
    parser.add_argument("--e2e-wan", default="", help="playwright wan diagnostics json")
    parser.add_argument("--e2e-cache", default="", help="playwright cache diagnostics json")
    parser.add_argument("--output", default="-", help="markdown path or - for stdout")
    args = parser.parse_args()

    probe = _load(args.probe)
    e2e_wan = _load(args.e2e_wan)
    e2e_cache = _load(args.e2e_cache)

    lines = ["# Playback WAN diagnostics report", ""]
    if probe:
        lines.append("## Server probe")
        summary = probe.get("summary") or {}
        if "c1_c2_ratio" in summary:
            lines.append(f"- C1/C2 memory ratio: **{summary['c1_c2_ratio']}×**")
        for name, data in (summary.get("scenarios") or {}).items():
            lines.append(f"### {name}")
            lines.append(f"- timeline p50: {data.get('timeline_p50')}")
            lines.append(f"- cache headers: {data.get('cache_headers')}")
            lines.append(f"- stale: {data.get('stale')}")
            lines.append(f"- 503/errors: {data.get('errors503')}")
            if data.get("notes"):
                lines.append(f"- notes: {', '.join(data['notes'])}")
        lines.append("")

    if e2e_wan:
        lines.append("## E2E WAN")
        lines.append(f"```json\n{json.dumps(e2e_wan, indent=2, ensure_ascii=False)}\n```")
        lines.append("")

    if e2e_cache:
        lines.append("## E2E cache (C1–C6)")
        lines.append(f"```json\n{json.dumps(e2e_cache, indent=2, ensure_ascii=False)}\n```")
        lines.append("")

    text = "\n".join(lines)
    if args.output == "-":
        print(text)
    else:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
