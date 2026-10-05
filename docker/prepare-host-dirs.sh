#!/usr/bin/env bash
# Prepare host directories and credentials.json for Docker Compose.
# Run from the EvilEye repository root:
#   ./docker/prepare-host-dirs.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p EvilEyeData/images videos models configs logs postgres_data

PROTO="$ROOT/evileye/credentials_proto.json"
CREDS="$ROOT/credentials.json"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"

if [[ ! -f "$CREDS" ]]; then
  if [[ ! -f "$PROTO" ]]; then
    echo "error: missing $PROTO" >&2
    exit 1
  fi
  cp "$PROTO" "$CREDS"
  echo "Created credentials.json from credentials_proto.json"
fi

POSTGRES_PASSWORD="$POSTGRES_PASSWORD" python3 - <<'PY'
import json
import os
from pathlib import Path

password = os.environ.get("POSTGRES_PASSWORD") or "postgres"
p = Path("credentials.json")
data = json.loads(p.read_text(encoding="utf-8"))
db = data.setdefault("database", {})
if not db.get("user_name"):
    db["user_name"] = "postgres"
if not db.get("password"):
    db["password"] = password
if not db.get("database_name"):
    db["database_name"] = "evil_eye_db"
db["host_name"] = "db"
if not db.get("port"):
    db["port"] = 5432
if not db.get("admin_user_name"):
    db["admin_user_name"] = db.get("user_name") or "postgres"
if not db.get("admin_password"):
    db["admin_password"] = db.get("password") or password
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print('Ensured credentials.json database.host_name="db" and non-empty DB password')
PY

if [[ ! -f "$ROOT/.env" ]]; then
  cat > "$ROOT/.env" <<EOF
EVILEYE_IMAGE=evileye/app:latest
EVILEYE_HOST_PORT=8181
EVILEYE_PG_PORT=5432
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
EOF
  echo "Created .env with POSTGRES_PASSWORD"
elif ! grep -q '^POSTGRES_PASSWORD=' "$ROOT/.env"; then
  echo "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" >> "$ROOT/.env"
  echo "Appended POSTGRES_PASSWORD to .env"
fi

SAMPLE_SRC="$ROOT/evileye/samples_configs/single_video.json"
SAMPLE_DST="$ROOT/configs/single_video.json"
if [[ -f "$SAMPLE_SRC" && ! -f "$SAMPLE_DST" ]]; then
  cp "$SAMPLE_SRC" "$SAMPLE_DST"
  echo "Copied sample configs/single_video.json"
fi

echo "Host dirs ready under: $ROOT"
echo "  EvilEyeData/ videos/ models/ configs/ logs/ postgres_data/"
echo "Next: make docker-up"
echo "  # or: docker compose --project-directory . -f docker/docker-compose.yml up -d --build"
