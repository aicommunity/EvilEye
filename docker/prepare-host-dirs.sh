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

if [[ ! -f "$CREDS" ]]; then
  if [[ ! -f "$PROTO" ]]; then
    echo "error: missing $PROTO" >&2
    exit 1
  fi
  cp "$PROTO" "$CREDS"
  echo "Created credentials.json from credentials_proto.json"
fi

python3 - <<'PY'
import json
from pathlib import Path
p = Path('credentials.json')
data = json.loads(p.read_text(encoding='utf-8'))
db = data.setdefault('database', {})
db.setdefault('user_name', 'postgres')
db.setdefault('password', 'postgres')
db.setdefault('database_name', 'evil_eye_db')
db['host_name'] = 'db'
db.setdefault('port', 5432)
db.setdefault('admin_user_name', db.get('user_name', 'postgres'))
db.setdefault('admin_password', db.get('password', 'postgres'))
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('Ensured credentials.json database.host_name="db"')
PY

SAMPLE_SRC="$ROOT/evileye/samples_configs/single_video.json"
SAMPLE_DST="$ROOT/configs/single_video.json"
if [[ -f "$SAMPLE_SRC" && ! -f "$SAMPLE_DST" ]]; then
  cp "$SAMPLE_SRC" "$SAMPLE_DST"
  echo "Copied sample configs/single_video.json"
fi

echo "Host dirs ready under: $ROOT"
echo "  EvilEyeData/ videos/ models/ configs/ logs/ postgres_data/"
echo "Next: docker compose -f docker/docker-compose.yml up -d --build"
