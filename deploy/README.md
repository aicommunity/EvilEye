# Deploy helpers

Site-facing ops tooling shipped with EvilEye (not the detection pipeline).

- [`monitor/`](monitor/) — systemd user watchdog / auto-restart / incident collection  
  Packaged mirror used by `evileye deploy`: `evileye/deploy_monitor/`  
  Keep both trees in sync when editing scripts.

## Site bring-up

```bash
pip install -e /path/to/EvilEye   # or: pip install evileye
# optional: sudo apt install libturbojpeg
evileye setup-web                 # ensure API Python deps + SPA static
evileye deploy                    # credentials, configs/, monitor/ + ensure Web UI service
# Open http://127.0.0.1:8181 and finish Basic setup in the UI
# Optional watchdog timers (separate from app service):
# DEPLOY_DIR=$PWD ./monitor/scripts/install_timer.sh
```

`evileye deploy` copies monitor files into the current site directory and **ensures**
the Web UI OS service (`evileye service-install`). Watchdog timers are still **not**
enabled automatically. See [`monitor/README.md`](monitor/README.md) and
[`../docs/CLI_SERVICE_COMMANDS.md`](../docs/CLI_SERVICE_COMMANDS.md).

- **App service** (`evileye.service`): runs `evileye server` for Web UI / API.
- **Watchdog** (`evileye-watchdog.*`): health-check / restart helpers for long-running pipeline jobs.

Web UI details: [`../docs/CLI_SETUP_WEB.md`](../docs/CLI_SETUP_WEB.md), [`../docs/WEB_UI_GUIDE.md`](../docs/WEB_UI_GUIDE.md).

**Alternative (GPU container):** [`../docs/DOCKER_DEPLOYMENT.md`](../docs/DOCKER_DEPLOYMENT.md) — Docker Compose + optional host CLI wrappers. Does not replace the pip install flow above.
