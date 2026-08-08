#!/usr/bin/env python3
"""Load smoke for Live grid preview WebSocket.

Connect N clients to /api/v1/runs/{rid}/ws/live, subscribe to source_ids,
optionally wait for preview messages. Use with auth disabled or pass --cookie.

Example:
  python scripts/ws_live_preview_load.py --run-id 1 --clients 20 --source-ids 0,1,2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time


async def _one_client(
    url: str,
    source_ids: list[int],
    duration_sec: float,
    cookie: str | None,
    stats: dict,
) -> None:
    try:
        import websockets
    except ImportError:
        print("Install websockets: pip install websockets", file=sys.stderr)
        raise SystemExit(2)

    headers = {}
    if cookie:
        headers["Cookie"] = cookie
    try:
        async with websockets.connect(url, additional_headers=headers or None) as ws:
            stats["connected"] += 1
            await ws.send(json.dumps({"op": "subscribe", "source_ids": source_ids}))
            deadline = time.monotonic() + duration_sec
            while time.monotonic() < deadline:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    await ws.send(json.dumps({"op": "ping"}))
                    continue
                if isinstance(msg, (bytes, bytearray)):
                    stats["binary"] += 1
                    stats["bytes"] += len(msg)
                else:
                    try:
                        payload = json.loads(msg)
                    except Exception:
                        continue
                    if payload.get("op") == "pong":
                        continue
                    if payload.get("type") in {"preview", "preview_notify"}:
                        stats["headers"] += 1
    except Exception as exc:
        stats["errors"] += 1
        stats["last_error"] = str(exc)


async def main_async(args: argparse.Namespace) -> int:
    base = args.base.rstrip("/")
    url = f"{base}/api/v1/runs/{args.run_id}/ws/live"
    source_ids = [int(x) for x in args.source_ids.split(",") if x.strip() != ""]
    stats = {
        "connected": 0,
        "headers": 0,
        "binary": 0,
        "bytes": 0,
        "errors": 0,
        "last_error": "",
    }
    started = time.monotonic()
    await asyncio.gather(
        *[
            _one_client(url, source_ids, args.duration, args.cookie, stats)
            for _ in range(args.clients)
        ]
    )
    elapsed = time.monotonic() - started
    print(
        json.dumps(
            {
                "url": url,
                "clients": args.clients,
                "duration_sec": args.duration,
                "elapsed_sec": round(elapsed, 2),
                **stats,
            },
            indent=2,
        )
    )
    return 0 if stats["errors"] == 0 or stats["connected"] > 0 else 1


def main() -> None:
    p = argparse.ArgumentParser(description="WS live preview load smoke")
    p.add_argument("--base", default="ws://127.0.0.1:8181", help="ws://host:port")
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--clients", type=int, default=20)
    p.add_argument("--source-ids", default="0,1,2,3,4")
    p.add_argument("--duration", type=float, default=10.0)
    p.add_argument("--cookie", default=None, help='e.g. "session=..."')
    args = p.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
