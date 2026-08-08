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
evileye deploy                    # credentials, configs/, monitor/
# then create/run a config; optionally enable watchdog timers
```

`evileye deploy` copies monitor files into the current site directory but **does not**
enable timers or start processes. See [`monitor/README.md`](monitor/README.md).

Web UI details: [`../docs/CLI_SETUP_WEB.md`](../docs/CLI_SETUP_WEB.md), [`../docs/WEB_UI_GUIDE.md`](../docs/WEB_UI_GUIDE.md).

**Alternative (GPU container):** [`../docs/DOCKER_DEPLOYMENT.md`](../docs/DOCKER_DEPLOYMENT.md) — Docker Compose + optional host CLI wrappers. Does not replace the pip install flow above.
