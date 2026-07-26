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
# 1. Prepare a site directory (configs + credentials)
mkdir -p /path/to/site && cd /path/to/site
evileye deploy
# copy/create your config, e.g. configs/poly-cameras-gst.json

# 2. Install watchdog timers from the EvilEye checkout
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

## Environment

| Variable | Meaning | Default |
|---|---|---|
| `DEPLOY_DIR` | Site root (`configs/`, `logs/`) | parent of `MONITOR_DIR` |
| `MONITOR_DIR` | Runtime monitor state | parent of `scripts/` |
| `CONFIG_NAME` | Config for `evileye run` | `poly-cameras-gst.json` |
| `DISPLAY` / `XAUTHORITY` | GUI session for restarts | auto / `.display_env` |
