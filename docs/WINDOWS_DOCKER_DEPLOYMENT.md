# Windows: Docker Desktop deployment

Official Windows path for the EvilEye container stack on **Docker Desktop (WSL2)**.

Native pip (no Docker): [WINDOWS_NATIVE.md](WINDOWS_NATIVE.md).  
Linux Docker / empty-folder bootstrap: [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md).

## Requirements

- Windows 10/11 with WSL2
- [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) (Compose v2)
- PowerShell 5.1+ (built into Windows) for host-cli
- Optional GPU: current NVIDIA Windows driver (WSL2 GPU); verify:

```powershell
docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi
```

- Corporate Docker Desktop licensing may apply — check Docker terms.

**Host CLI:** bash wrappers (`docker/install-host-cli.sh`) work in WSL/Git Bash. Native PowerShell/cmd use `.ps1` + `.cmd` (see [Host CLI (PowerShell)](#host-cli-powershell) below).

## Quick start (repository)

From the EvilEye repository root (PowerShell):

```powershell
.\docker\windows\Install-EvilEye.ps1 -EnableWatchdog
# optional host-cli into %LOCALAPPDATA%\EvilEye\bin pinned to this repo:
.\docker\windows\Install-EvilEye.ps1 -InstallHostCli
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

## Empty-folder bootstrap (Hub image)

```powershell
mkdir mysite; cd mysite
docker pull evileye/app:latest
docker run --rm -v "${PWD}:/site" -e EVILEYE_BOOTSTRAP_IMAGE=evileye/app:latest evileye/app:latest bootstrap
docker compose up -d
$env:Path = "$PWD\bin;$env:Path"
evileye --help
```

After bootstrap, `bin\` contains `evileye.cmd` / `evileye.ps1` and `EvilEye-DockerRun.ps1`. Site data (including `postgres_data\`) stays in the folder.

CPU image:

```powershell
docker pull evileye/app:cpu
docker run --rm -v "${PWD}:/site" -e EVILEYE_BOOTSTRAP_IMAGE=evileye/app:cpu evileye/app:cpu bootstrap
```

## Host CLI (PowerShell)

Commands `evileye`, `evileye-launch`, `evileye-process`, `evileye-configure`, `evileye-srv` on the host run inside the container via `docker run`. Relative paths (`configs\...`) resolve against the site directory mounted at `/site`.

### Scenario A — site-local `bin\` (after bootstrap)

```powershell
cd C:\path\to\mysite
$env:Path = "$PWD\bin;$env:Path"
evileye --help
evileye run configs/single_video.json --no-gui
```

Wrappers set `EVILEYE_DOCKER_SITE_DIR` to the parent of `bin\` automatically.

### Scenario B — global install pinned to a site

```powershell
.\docker\windows\Install-HostCli.ps1 -SiteDir 'C:\EvilEye\mysite' -Image evileye/app:latest
evileye --help
```

Default install prefix: `%LOCALAPPDATA%\EvilEye\bin` (added to User PATH).

Without `-SiteDir`, install uses pwd-mode (mounts the current directory), similar to Linux `install-host-cli.sh`.

Uninstall:

```powershell
.\docker\windows\Uninstall-HostCli.ps1
```

Removes only files marked as EvilEye docker host-cli. If the prefix directory becomes empty, it is also removed from User PATH.

### Scenario C — repository installer

```powershell
.\docker\windows\Install-EvilEye.ps1 -InstallHostCli
```

Pins host-cli to the repo root (`-SiteDir $Root`).

### GPU / CPU

- GPU image (`evileye/app:latest`): default `EVILEYE_DOCKER_GPU_MODE=gpus` (`--gpus all`).
- CPU image (`evileye/app:cpu`): wrappers default `EVILEYE_DOCKER_GPU_MODE=none`.
- No NVIDIA on a GPU image: `$env:EVILEYE_DOCKER_GPU_MODE = 'none'`.

### Conflict with pip / native install

Do not mix `pip install evileye` entry points and Docker host-cli in the same PATH. `Install-HostCli.ps1` warns if `evileye` already points at a non–host-cli file.

### Environment variables

- `EVILEYE_DOCKER_IMAGE` — image tag (default `evileye/app:latest`)
- `EVILEYE_DOCKER_SITE_DIR` — host site path (set by site wrappers)
- `EVILEYE_DOCKER_GPU_MODE` — `gpus` | `cdi` | `none`
- `EVILEYE_DATA_DIR` — optional; site-mode default `/site/EvilEyeData`
- `EVILEYE_DOCKER_EXTRA_ARGS` — extra `docker run` flags (space-separated)

## Compose services

[docker/docker-compose.yml](../docker/docker-compose.yml) (and bootstrap-generated `docker-compose.yml`):

| Service | Role |
|---------|------|
| `app` | `evileye run configs/single_video.json --no-gui` (pipeline) |
| `web` | `evileye server --host 0.0.0.0 --port 8181` (Web UI/API) |
| `db` | Postgres 15 (`./postgres_data` bind mount by default) |

All use `restart: unless-stopped`. Port **8181** is published by `web`.

### Compose env overrides

```powershell
$env:EVILEYE_IMAGE = "evileye/app:latest"   # or evileye/app:cpu
$env:EVILEYE_SITE_DIR = "C:\EvilEye\mysite" # host folder mounted as /site
$env:EVILEYE_HOST_PORT = "8181"
$env:EVILEYE_PG_PORT = "5432"
$env:EVILEYE_PG_DATA = "C:\EvilEye\mysite\postgres_data"
```

Inside the container the site is `/site`. Use **relative** config paths (`videos/...`, `EvilEyeData`) as in packaged samples.

> Note: older docs referred to `EVILEYE_HOST_DATA` / per-folder mounts. Current compose mounts the whole site directory (`EVILEYE_SITE_DIR`).

Ensure the site path is shared with Docker Desktop (Settings → Resources → File sharing) if it is not under your user profile.

## Credentials

`database.host_name` must be **`db`** for Compose Postgres. `Prepare-HostDirs.ps1` / bootstrap set this when creating credentials.

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

## Offline / release zip

See `scripts/windows/Build-DockerReleaseZip.ps1` (exports image + scripts). Base image Ultralytics (GPU) is **AGPL** — review license for commercial use.

## Troubleshooting

- **credentials mount error** — run `Prepare-HostDirs.ps1` or bootstrap first so `credentials.json` is a file.
- **`evileye` not found** — add `bin` to PATH for this session (`$env:Path = "$PWD\bin;$env:Path"`), or re-open the terminal after `Install-HostCli.ps1`. Confirm `evileye.cmd` exists under `bin`.
- **ExecutionPolicy** — `.cmd` shims call PowerShell with `-ExecutionPolicy Bypass`; you do not need to change the system policy.
- **GPU unavailable** — driver, WSL2, Docker Desktop GPU settings; or `$env:EVILEYE_DOCKER_GPU_MODE='none'`.
- **Wrong files / empty configs** — ensure `EVILEYE_DOCKER_SITE_DIR` / site-local wrappers point at the intended folder.
- **Image missing** — `docker pull evileye/app:latest` (or `:cpu`).
- **UI down but app up** — check `docker logs evileye_web`; watchdog reasons include `ui_unreachable` / `container_missing_web`.
- Do not mix pip `evileye` with Docker host-cli in the same PATH.

## Related

- [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md)
- [WINDOWS_NATIVE.md](WINDOWS_NATIVE.md)
- [CLI_DEPLOY_COMMAND.md](CLI_DEPLOY_COMMAND.md)
