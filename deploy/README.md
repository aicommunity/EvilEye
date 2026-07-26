# Deploy helpers

Site-facing ops tooling shipped with EvilEye (not the detection pipeline).

- [`monitor/`](monitor/) — systemd user watchdog / auto-restart / incident collection  
  Packaged mirror used by `evileye deploy`: `evileye/deploy_monitor/`  
  Keep both trees in sync when editing scripts.

`evileye deploy` copies these files into the current site directory but **does not**
enable timers or start processes. See [`monitor/README.md`](monitor/README.md).
