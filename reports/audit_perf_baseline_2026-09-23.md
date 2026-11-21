# Audit perf baseline — 2026-09-23

Captured after Stage 0–1 ACL/functional fixes, before Stage 2 optimizations (A12, B01–B06).

## Environment

- Host: Linux development machine (no dedicated multi-camera live stand in this session).
- Browser Network/Performance/React Profiler: **not** captured (no live multi-cam UI session).
- Server metrics from unit/integration tests and code instrumentation points.

## Code-level baselines (pre-optimization)

| Area | Observation | Metric proxy |
|------|-------------|--------------|
| Live WS | Subscribe all cameras on LivePage (`previewByRun` = all cams) | bytes_sent grows with camera count, not viewport |
| Snapshot notify | Fixed in A06 (no false 304) | 304 only after applied etag |
| Playback `_memory_cache` | Unbounded dict + deepcopy under lock | keys grow with seek/ts/windows |
| Detection index UI | Day-wide fetch preferred when `dayBounds` set | larger first payload vs viewport |
| Metadata REST fallback | Per-source poll every 1.5s without abort | N concurrent GETs under WS down |
| Journal feed | load/poll without generation cancel | stale responses can win races |
| `asyncio.wait_for(to_thread)` | Timeout returns 503 but worker continues | in-flight threads after client timeout |

## Unit-test smoke (this session)

- ACL/security matrix A01–A05: pass
- Frontend vitest: 168 tests pass
- Playback index coverage A09/A10: pass

## Target after Stage 2 (compare on same archive)

1. Live WS: subscribe only visible tiles → lower `bytes_sent` at 16 cams with ~4 visible.
2. `_memory_cache`: capped keys/bytes; no unbounded growth on 10 min seek scrub.
3. Detection markers: viewport-first TTFM; day enrich deferred.
4. REST fallback: ≤1 in-flight cycle; abort on reconnect.
5. Journal: filter switch cancels prior load; no duplicate append.

## How to re-measure

```bash
# Server (with live stack)
evileye status
python scripts/ws_live_preview_load.py --run-id <id> --clients 4

# Frontend
cd evileye/api/frontend && npm test && npm run build
# Browser: Performance + React Profiler on Live / Playback seek
```
