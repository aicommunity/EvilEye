#!/usr/bin/env python3
"""Audit client_diag for a day/user; optionally correlate with playback timeouts in main logs.

Usage:
  python3 scripts/audit_client_diag_day.py --day 20260910 --user onmatsko@gmail.com
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

DEPLOY_LOGS = Path("/home/user/EvilEyeDeploy/logs")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True, help="YYYYMMDD")
    ap.add_argument("--user", default="")
    ap.add_argument("--correlate-timeouts", action="store_true")
    args = ap.parse_args()

    diag = DEPLOY_LOGS / f"client_diag_{args.day}.log"
    if not diag.is_file():
        # fallback repo logs
        diag = Path(__file__).resolve().parents[1] / "logs" / f"client_diag_{args.day}.log"
    if not diag.is_file():
        print(json.dumps({"ok": False, "error": f"missing {diag}"}))
        return 1

    kinds = collections.Counter()
    pages = collections.Counter()
    rs = collections.Counter()
    ws_codes = collections.Counter()
    seeks = 0
    n = 0
    ts_min = ts_max = None
    with diag.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if args.user and args.user not in line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if args.user and row.get("user") != args.user:
                continue
            n += 1
            pages[row.get("page") or "?"] += 1
            ev = row.get("event") or {}
            kind = ev.get("kind") or "?"
            kinds[kind] += 1
            p = ev.get("payload") or {}
            if kind == "slot_state":
                rs[str(p.get("readyState"))] += 1
            if kind == "timeline_seek":
                seeks += 1
            if kind == "ws_close":
                ws_codes[str(p.get("code"))] += 1
            ts = row.get("ts")
            if isinstance(ts, (int, float)):
                ts_min = ts if ts_min is None else min(ts_min, ts)
                ts_max = ts if ts_max is None else max(ts_max, ts)

    out = {
        "ok": True,
        "day": args.day,
        "user": args.user or "*",
        "events": n,
        "pages": dict(pages),
        "kinds": dict(kinds.most_common(20)),
        "readyState": dict(rs),
        "ws_close_codes": dict(ws_codes),
        "timeline_seeks": seeks,
        "ts_window": [ts_min, ts_max],
    }

    if args.correlate_timeouts and ts_min and ts_max:
        # Rough: scan main logs for playback_timeline timeout near wall clock derived from day file
        # Prefer textual day match in filenames + timeout lines
        timeout_hits = []
        day_dash = f"{args.day[:4]}-{args.day[4:6]}-{args.day[6:8]}"
        for fp in sorted(DEPLOY_LOGS.glob("*_evileye_main.log*")):
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                if "playback_timeline timeout" in line or "playback media high inflight" in line or "playback_media busy" in line:
                    if day_dash in line or args.day in fp.name:
                        timeout_hits.append(line.strip()[-220:])
        out["server_timeout_samples"] = timeout_hits[:30]
        out["server_timeout_count"] = len(timeout_hits)

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
