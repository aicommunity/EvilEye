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
| `GET /state/cameras?scope=current` | 200 | 1.6 KiB | **4.8** | **6.8** | ~8 |
| `GET /runs/{rid}/snapshot` 1 cam | 200 | **94 KiB** | **7.3** | **10.3** | — |
| `snapshot` 4 cams (sequential wall) | 200 | **421 KiB** | **26.1** | **32.6** | — |
| `snapshot` 5 cams | 200 | **539 KiB** | **37.8** | **41.0** | — |
| `GET /playback/timeline` (Cam1) | 200 | **878 KiB** | **115** | **292** | — |
| `GET /playback/detections` (Cam1, limit=500) | 200 | **3.94 MiB** | **637** | **793** | — |
| `GET /playback/events` (day) | 200 | 201 KiB | **42** | **62** | — |

Snapshot path: `/api/v1/runs/{rid}/snapshot?source_id=`. Live WS `bytes_sent` not separately instrumented in this probe (use `scripts/ws_live_preview_load.py` for fan-out).

## Observations vs prior baseline notes

1. **state** hot path is already fast (p95 &lt; 10 ms) under current semaphore; queue wait is included in the deadline (R07).
2. **timeline** warm responses are large (~0.9 MiB) with p95 ~145 ms — candidates for cache hit rate / payload trim.
3. **detections** day camera window was heavy with `limit=500`; probe now uses UI-style `ticks_only=true` (R17).
4. **events** day ACL-filtered payload ~200 KiB / p95 ~57 ms — acceptable for day open; index build is uncapped with `covered_cameras` (R05).
5. `playback_cache` stores entry nbytes, keeps sticky/stale on fresh miss (R06/R15); `/ready` exposes `playback_memory_cache` + `state_thread_stats`.
6. Media ACL runs after canonicalize; live WS refreshes ACL on ping/subscribe (R01/R02/R08).

## B07 SPA (build-time)

After `evileye web build --force` (2026-09-23 F4):

| Metric | Value |
|--------|-------|
| Initial `index-*.js` | **238 KiB** (`index-BYSWqj5z.js`) |
| Lazy JS chunks | **33** |
| Total JS under `static/assets` | ~540 KiB |

TTI / React Profiler: not measured in headed browser this pass; lazy route split already in `App.tsx`.

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

Remeasure after A12/B04/B05/B06 (same probe, post-`systemctl --user restart evileye`):

| Endpoint | p50 ms | p95 ms | bytes p50 | notes |
|----------|--------|--------|-----------|-------|
| state.cameras | 6.1 | 7.9 | 1.6 KiB | stable |
| snapshot 1/4/5 | 7.6 / 33 / 38 | 9.4 / 44 / 43 | up to ~533 KiB | cold 404 on first cam briefly |
| timeline | **106** | **266** | 878 KiB | p50 slightly improved vs before |
| detections | 669 | 849 | ~4.2 MiB | payload-bound |
| events | **37** | 316 | 201 KiB | p50 improved; p95 outlier |

`memory_cache_stats` now reports `bytes_est` / `copy_ms` / `thread_inflight` (A12/B06). No growth of in-flight counters on repeated probe. Browser Profiler not re-captured.

## After reaudit gap follow-up (R01–R17 + F1)

Git SHA: `74ac723` (+ SPA rebuild). Probe: `scripts/audit_perf_probe.py` → [`reports/audit_perf_probe_reaudit.json`](audit_perf_probe_reaudit.json), samples [`reports/audit_perf_samples_2026-09-23.jsonl`](audit_perf_samples_2026-09-23.jsonl). `--reps 5`, Cam1, date `2026-09-23`. Aux via `GET /ready` (embeds `playback_memory_cache` + `state_thread_stats`).

| Endpoint | p50 ms | p95 ms | bytes p50 | notes |
|----------|--------|--------|-----------|-------|
| timeline | 190 | 377 | ~1.55 MiB | codes 200 |
| detections (`ticks_only=true`) | **457** | **622** | ~3.05 MiB | smaller than old limit=500 full payload |
| events | **37** | **51** | 201 KiB | stable |
| media (segment path from timeline) | ~2041 | ~2059 | large body | path extraction fixed (R17) |

R09 SPA: `authEpoch` in cache keys + ACL-revision bump shipped in same wave; restart applied after `evileye web build`.
