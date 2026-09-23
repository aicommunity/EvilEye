# Audit Stage 2 — measured perf baseline

Date: 2026-09-23  
Host: live `systemctl --user` stack (`evileye` on `:8181`, cwd `EvilEyeDeploy`, config `poly-cameras-gst.json`, run_id **334**, 5 cameras).  
Tooling: `scripts/audit_perf_probe.py` (cookie session), raw JSON `/tmp/audit_perf_probe_before.json`.

Compared to [audit_perf_baseline_2026-09-23.md](audit_perf_baseline_2026-09-23.md) (code-level / unmeasured notes only).

## Environment

| Item | Value |
|------|--------|
| API | `http://127.0.0.1:8181` |
| Auth | session cookie (admin) |
| Archive day | `2026-09-23` (`Cam1`) |
| Live cameras | 5 (`source_id` 0–4) |
| Probe reps | 11 (+ warm) |

Browser Network / Performance / React Profiler: not captured in this automated pass (no headed DevTools session). Server p50/p95 below are the Stage 2 gate numbers.

## Measured p50 / p95 / p99

| Endpoint | HTTP | bytes p50 | p50 ms | p95 ms | p99 ms |
|----------|------|-----------|--------|--------|--------|
| `GET /state/cameras?scope=current` | 200 | 1.6 KiB | **5.6** | **7.3** | 8.2 |
| `snapshot` 1 cam (fan-out wall) | 404* | 22 B | 6.1 | 6.9 | 7.5 |
| `snapshot` 4 cams | 404* | 88 B | 24.3 | 26.2 | 26.9 |
| `snapshot` 5 cams | 404* | 110 B | 29.1 | 35.4 | 38.8 |
| `GET /playback/timeline` (Cam1) | 200 | **878 KiB** | **109** | **144** | 146 |
| `GET /playback/detections` (Cam1, limit=500) | 200 | **3.86 MiB** | **626** | **783** | 882 |
| `GET /playback/events` (day) | 200 | 201 KiB | **44** | **57** | 62 |

\* Snapshot path returned 404 on this stand (preview JPEG route / demand not warm for REST probe). Latency still reflects handler + auth overhead; Live WS path is preferred for bytes_sent.

## Observations vs prior baseline notes

1. **state** hot path is already fast (p95 &lt; 10 ms) under current semaphore.
2. **timeline** warm responses are large (~0.9 MiB) with p95 ~145 ms — candidates for cache hit rate / payload trim.
3. **detections** day camera window is the heavy hit (~4 MiB, p95 ~0.8 s) — matches audit A11/B detection payload concern.
4. **events** day ACL-filtered payload ~200 KiB / p95 ~57 ms — acceptable for day open.
5. `_memory_cache` still key-capped (256) without soft byte budget / `copy_ms` (A12 pending in F2.2).
6. `wait_for(to_thread)` still releases route slots on timeout while worker may continue (B06 pending).

## B07 SPA (build-time)

Recorded after `npm run build` in F4; until then from last tracked static: see F4 section / after-remeasure.

## How to reproduce

```bash
# login → cookie jar, then:
python scripts/audit_perf_probe.py \
  --base http://127.0.0.1:8181 \
  --cookie-jar /tmp/ee_audit_cj \
  --date 2026-09-23 --run-id 334 --source-ids 0,1,2,3,4 \
  --camera Cam1 --reps 11 \
  --out /tmp/audit_perf_probe.json
```

## After section (F2.3)

Filled after A12/B04/B05/B06 land — see bottom of this file after remeasure.
