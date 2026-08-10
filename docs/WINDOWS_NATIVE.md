# Windows: native pip install

Supported path for running EvilEye directly on Windows (no Docker).

## Requirements

- Windows 10/11
- Python **3.10+** (recommend 3.11)
- Optional: NVIDIA drivers + CUDA-compatible PyTorch/ORT wheels for GPU
- Optional: PostgreSQL for DB mode (or use JSON / disable DB in setup)
- GStreamer / PyGObject is **optional**; OpenCV capture is the default fallback

## Install

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install "evileye[win]"
# from source:
# pip install -e ".[win]"
```

The `[win]` extra pins CPU `onnxruntime`. Main dependencies already pin `onnxruntime-gpu` for Windows (`<1.20.2`). Prefer one ORT stack; see pip resolver output if both conflict.

Helper script (from repo checkout):

```powershell
.\scripts\windows\Install-EvilEyeNative.ps1 -SiteDir "$env:USERPROFILE\EvilEye"
```

## Site bring-up

Run commands from your **site directory** (or set `EVILEYE_SITE_DIR`):

```powershell
mkdir $env:USERPROFILE\EvilEye
cd $env:USERPROFILE\EvilEye
$env:EVILEYE_SITE_DIR = (Get-Location).Path

evileye setup-web
evileye deploy
# Open http://127.0.0.1:8181 — admin bootstrap password is in the server log
evileye service-install
```

Sample pipeline:

```powershell
evileye deploy-samples
evileye run configs/single_video.json --no-gui
```

## Environment

| Variable | Meaning |
|----------|---------|
| `EVILEYE_SITE_DIR` | Site root (`credentials.json`, `configs/`, `logs/`, `monitor/`) |
| `EVILEYE_DATA_DIR` | Writable media/data directory (default `EvilEyeData`) |
| `EVILEYE_LOG_SESSION_ID` | Force shared log session id across child processes |

Paths in packaged samples under `evileye/samples_configs/` are **relative** (`videos/...`, `EvilEyeData`).

## Credentials / database

`credentials.json` uses **`database.host_name`** (not `host`). For local Postgres:

```json
"database": {
  "user_name": "postgres",
  "password": "postgres",
  "database_name": "evil_eye_db",
  "host_name": "localhost",
  "port": 5432,
  "admin_user_name": "postgres",
  "admin_password": "postgres"
}
```

Or complete Basic setup in the Web UI without Postgres (JSON journals).

## OS service (Web UI)

```powershell
# Prefer elevated shell for schtasks
evileye service-install
evileye service-uninstall
```

Creates `scripts\evileye-server.bat` and Scheduled Task **EvilEye** (`ONSTART`). See [CLI_SERVICE_COMMANDS.md](CLI_SERVICE_COMMANDS.md).

## Native watchdog

Separate from Linux `monitor/scripts/install_timer.sh`:

```powershell
evileye watchdog-install --config configs/single_video.json
evileye watchdog-check --config configs/single_video.json
evileye watchdog-morning
evileye watchdog-uninstall
```

Writes `monitor/journal.jsonl`, incidents, and morning reports. Restarts use process-tree terminate + detached `evileye run`.

| Path | Watchdog |
|------|----------|
| Linux systemd | `install_timer.sh` |
| Windows native pip | `evileye watchdog-install` |
| Windows Docker | `docker/windows/Install-Watchdog.ps1` |

## Smoke checklist

```text
evileye info
evileye setup-web
evileye deploy
evileye server --host 127.0.0.1 --port 8181
# curl http://127.0.0.1:8181/ready
evileye deploy-samples
evileye run configs/single_video.json --no-gui
evileye service-install --dry-run
evileye watchdog-install --dry-run
```

## Limitations

- Full GStreamer/NVDEC parity with Linux Docker is **not** promised.
- Linux bash monitor (PSS/`/proc`/X11) is not used on Windows.
- PyQt GUI is best-effort; headless `server` / `run --no-gui` is the primary path.
- For GPU + GStreamer container parity use [WINDOWS_DOCKER_DEPLOYMENT.md](WINDOWS_DOCKER_DEPLOYMENT.md).

## Related

- [CLI_DEPLOY_COMMAND.md](CLI_DEPLOY_COMMAND.md)
- [CLI_SETUP_WEB.md](CLI_SETUP_WEB.md)
- [WEB_UI_GUIDE.md](WEB_UI_GUIDE.md)
- [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md)
