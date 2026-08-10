# Windows: Docker Desktop deployment

Official Windows path for the GPU Ultralytics container stack on **Docker Desktop (WSL2)**.

Native pip (no Docker): [WINDOWS_NATIVE.md](WINDOWS_NATIVE.md).  
Linux Docker: [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md).

## Requirements

- Windows 10/11 with WSL2
- [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) (Compose v2)
- Optional GPU: current NVIDIA Windows driver (WSL2 GPU); verify:

```powershell
docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi
```

- Corporate Docker Desktop licensing may apply — check Docker terms.

**Note:** bash `docker/install-host-cli.sh` is **Linux/WSL-only**. On Windows use the PowerShell scripts below.

## Quick start

From the EvilEye repository root (PowerShell):

```powershell
.\docker\windows\Install-EvilEye.ps1 -EnableWatchdog
# UI
start http://127.0.0.1:8181
```

Or step by step:

```powershell
.\docker\windows\Prepare-HostDirs.ps1
# credentials.json database.host_name is set to "db"
.\docker\windows\Start-EvilEye.ps1
.\docker\windows\Install-Watchdog.ps1
```

Stop:

```powershell
.\docker\windows\Stop-EvilEye.ps1
.\docker\windows\Uninstall-Watchdog.ps1
```

## Compose services

[docker/docker-compose.yml](../docker/docker-compose.yml):

| Service | Role |
|---------|------|
| `app` | `evileye run configs/single_video.json --no-gui` (pipeline) |
| `web` | `evileye server --host 0.0.0.0 --port 8181` (Web UI/API) |
| `db` | Postgres 15 |

All use `restart: unless-stopped`. Port **8181** is published by `web`.

### Host path env vars

Defaults are relative to the compose file (`../` = repo root). On Windows set absolute paths if needed:

```powershell
$env:EVILEYE_HOST_DATA = "C:\EvilEye\EvilEyeData"
$env:EVILEYE_HOST_VIDEOS = "C:\EvilEye\videos"
$env:EVILEYE_HOST_MODELS = "C:\EvilEye\models"
$env:EVILEYE_HOST_CONFIGS = "C:\EvilEye\configs"
$env:EVILEYE_HOST_LOGS = "C:\EvilEye\logs"
$env:EVILEYE_HOST_CREDENTIALS = "C:\EvilEye\credentials.json"
$env:EVILEYE_HOST_PORT = "8181"
```

Inside the container paths remain Unix (`/opt/evileye/...`). Use **relative** config paths (`videos/...`, `EvilEyeData`) as in packaged samples.

## Credentials

`database.host_name` must be **`db`** for Compose Postgres. `Prepare-HostDirs.ps1` rewrites `localhost` → `db` when creating/updating credentials.

## Docker watchdog

```powershell
.\docker\windows\Watch-EvilEye.ps1          # one shot
.\docker\windows\Install-Watchdog.ps1       # every 5 min + 09:00 report
```

Checks:

1. `evileye_app` / `evileye_web` running
2. `GET http://127.0.0.1:8181/ready`
3. Host `logs\*_evileye_main.log` freshness

On failure: incident under `monitor\incidents\` and `compose up -d`.

Journal schema matches the Linux monitor (`timestamp`, `status`, `reason`, `log_file`, `log_age_sec`).

## Offline / release zip

See `scripts/windows/Build-DockerReleaseZip.ps1` (exports image + scripts). Base image Ultralytics is **AGPL** — review license for commercial use.

## Troubleshooting

- **credentials mount error** — run `Prepare-HostDirs.ps1` first so `credentials.json` is a file.
- **GPU unavailable** — driver, WSL2, Docker Desktop GPU settings, `--gpus all`.
- **UI down but app up** — check `docker logs evileye_web`; watchdog reasons include `ui_unreachable` / `container_missing_web`.
- Do not mix pip `evileye` entry points with Linux host-cli wrappers in the same PATH.

## Related

- [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md)
- [WINDOWS_NATIVE.md](WINDOWS_NATIVE.md)
- [CLI_DEPLOY_COMMAND.md](CLI_DEPLOY_COMMAND.md)
