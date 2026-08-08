#!/usr/bin/env bash
# Prepare host directories and credentials.json for Docker Compose.
# Run from the EvilEye repository root:
#   ./docker/prepare-host-dirs.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p EvilEyeData/images videos models configs logs

PROTO="$ROOT/evileye/credentials_proto.json"
CREDS="$ROOT/credentials.json"

if [[ ! -f "$CREDS" ]]; then
  if [[ ! -f "$PROTO" ]]; then
    echo "error: missing $PROTO" >&2
    exit 1
  fi
  cp "$PROTO" "$CREDS"
  echo "Created credentials.json from credentials_proto.json"
else
  echo "credentials.json already exists, leaving as-is"
fi

# Hint for compose networking (app talks to service name "db")
if grep -q '"host_name"[[:space:]]*:[[:space:]]*"localhost"' "$CREDS" 2>/dev/null; then
  echo "note: for docker compose, set database.host_name to \"db\" in credentials.json"
fi

echo "Host dirs ready under: $ROOT"
echo "  EvilEyeData/ images videos models configs logs"
echo "Next: docker compose -f docker/docker-compose.yml up --build"
