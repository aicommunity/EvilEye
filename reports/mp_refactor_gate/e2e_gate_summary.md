# MP refactor gate (2026-05-22)

Environment: F2 (`EVILEYE_MP_DRAIN_POLL_SEC=0.01`, `EVILEYE_CONTROLLER_BACKPRESSURE=soft`)

## E2E 90s

| Config | e2e_tracker_fps | staleness_in_band | mean_staleness |
|--------|-------------------|-------------------|----------------|
| poly-videos (process) | 28.38 | **true** | 6.23 |
| poly-videos-thread | 9.15 | false | 24.52 |

**e2e_ratio** (process/thread): **3.10** (gate ≥ 3.0) — PASS

Artifacts: `e2e_process.json`, `e2e_thread.json`, `e2e_*.log`

## Soak MEM-4

- Script: `scripts/soak_mp_memory.sh`
- Config: `configs/poly-videos.json`
- Duration: 1800s (30 min), interval 60s
- Log: `soak_mp_rss.log`

| Phase | RSS (KB) |
|-------|----------|
| t+0 (launcher) | 9 652 |
| t+60s (steady) | 748 472 |
| t+30min | 748 472 |

**PASS:** после прогрева RSS **плоский** ~730 MB весь прогон (рост менее 0.1%, gate «нет +10% за 30 min»).

Soak завершён: `2026-05-22T17:54:30+03:00`, exit 0.
