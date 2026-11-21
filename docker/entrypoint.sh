#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "bootstrap" ]]; then
  shift
  exec python /opt/evileye/docker/bootstrap_site.py "$@"
fi

exec "$@"
