# EvilEye deploy monitor (watchdog)

Ops tooling that watches a running `evileye run` site, collects incidents, and
auto-restarts on failure. This is **not** part of the detection pipeline.

## Layout

```
deploy/monitor/                 # in the EvilEye git repo (source of truth)
├── scripts/                    # health_check, restart, install_timer, ...
└── systemd/                    # unit templates (install_timer expands them)

<site>/                         # runtime deploy directory (e.g. EvilEyeDeploy)
├── configs/
├── logs/
└── monitor/                    # created/synced by install_timer.sh
    ├── scripts/                # copy of package scripts
    ├── incidents/              # runtime (do not commit)
    ├── journal.jsonl           # runtime
    └── watchdog.log            # runtime
```

## Install on a new machine

```bash
# 1. Prepare a site directory
mkdir -p /path/to/site && cd /path/to/site
evileye deploy
# → creates credentials.json, configs/, logs/, monitor/ (scripts + systemd templates)
# → does NOT start EvilEye or enable systemd timers

# 2. Add/create your config, then optionally enable the watchdog:
DEPLOY_DIR=/path/to/site \
CONFIG_NAME=poly-cameras-gst.json \
DISPLAY=:1 \
  ./monitor/scripts/install_timer.sh
```

Or install timers from the EvilEye checkout without using the site copy:

```bash
cd /path/to/EvilEye
DEPLOY_DIR=/path/to/site \
CONFIG_NAME=poly-cameras-gst.json \
DISPLAY=:1 \
  ./deploy/monitor/scripts/install_timer.sh
```

`install_timer.sh` will:

- copy scripts into `$DEPLOY_DIR/monitor/scripts`
- write `~/.config/systemd/user/evileye-watchdog.{service,timer}`
- set **`KillMode=process`** (required — without it, oneshot kills EvilEye on exit)
- enable the 5-minute timer and morning report

## Manual commands

```bash
export DEPLOY_DIR=/path/to/site MONITOR_DIR=/path/to/site/monitor

$MONITOR_DIR/scripts/health_check.sh
$MONITOR_DIR/scripts/restart_evileye.sh "manual"
$MONITOR_DIR/scripts/morning_report.sh
systemctl --user status evileye-watchdog.timer
```

## Critical design notes

1. **`KillMode=process`** on the watchdog oneshot — default `control-group` caused a
   multi-week restart storm (process started, service exited, systemd killed EvilEye).
2. **`restart_evileye.sh`** launches via `systemd-run --user --scope` when available,
   and requires a boot marker (`GUI shown` / `Starting main application loop`) before
   declaring Restart OK.
3. Paths are env-driven (`DEPLOY_DIR`, `MONITOR_DIR`, `CONFIG_NAME`) — no hardcoded
   `/home/user/...` in the package scripts.
4. **`health_check.sh`** appends a memory snapshot to `monitor/memory_journal.jsonl`
   (RSS/PSS for parent, det-mp, tracker, host swap). Use it to distinguish leak vs
   high steady-state after config changes.

## Memory budget (≈62 GB hosts / poly-cameras)

Dominant cost is **one full YOLO copy per `det-mp-*` process**. Prefer:

| Knob | Recommended | Why |
|---|---|---|
| `pipeline.detectors[].num_detection_threads` | **1** | `3` ⇒ 15 YOLO processes (~2.3–2.5 GB RSS each) |
| `botsort_cfg.with_reid` | **false** unless `tracker_onnx` is set | ReID without onnx path is unused in process mode |
| `EVILEYE_MP_PENDING_CAP` / `EVILEYE_MP_PENDING_CAP_TRACKER` | 1–2 | Limits Frame+SHM held while jobs are in flight |
| `EVILEYE_EVENT_BUFFER_FPS_MAX` | 5 (default) | Caps EventBuffer when `event_buffer_fps` is null |

Do **not** raise `num_detection_threads` above 1 unless latency measurements prove a bottleneck **and** RAM/VRAM headroom exists. Prefer shared/fewer detector workers over per-ROI process multiplication.

Target: EvilEye tree PSS **&lt; ~20 GB**, host swap used **&lt; ~5 GB** in steady state.

## Environment

| Variable | Meaning | Default |
|---|---|---|
| `DEPLOY_DIR` | Site root (`configs/`, `logs/`) | parent of `MONITOR_DIR` |
| `MONITOR_DIR` | Runtime monitor state | parent of `scripts/` |
| `CONFIG_NAME` | Config for `evileye run` | `poly-cameras-gst.json` |
| `DISPLAY` / `XAUTHORITY` | GUI session for restarts | auto / `.display_env` |
| `EVILEYE_MP_PENDING_CAP` | Detector pending job depth | `max(roi_count, 1)` |
| `EVILEYE_MP_PENDING_CAP_TRACKER` | Tracker pending job depth | `2` |
| `EVILEYE_EVENT_BUFFER_FPS_MAX` | EventBuffer fps when config fps is null | `5` |
