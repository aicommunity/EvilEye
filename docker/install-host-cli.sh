#!/usr/bin/env bash
# EvilEye docker host-cli
# Install thin CLI wrappers into PREFIX (default: ~/.local/bin).
# Does NOT install the Python package on the host (opt-in Docker path only).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$ROOT/.." && pwd)"
SRC="$ROOT/host-cli"
PREFIX="${PREFIX:-$HOME/.local/bin}"
MARKER="# EvilEye docker host-cli"

NAMES=(
  evileye-docker-run.sh
  evileye
  evileye-launch
  evileye-process
  evileye-configure
  evileye-srv
)

if [[ ! -d "$SRC" ]]; then
  echo "error: missing $SRC" >&2
  exit 1
fi

mkdir -p "$PREFIX"

warn_existing() {
  local name="$1"
  local existing
  existing="$(command -v "$name" 2>/dev/null || true)"
  if [[ -z "$existing" ]]; then
    return 0
  fi
  if [[ -f "$existing" ]] && grep -qF "$MARKER" "$existing" 2>/dev/null; then
    return 0
  fi
  echo "warning: '$name' already exists at $existing (likely pip install)." >&2
  echo "         Docker host-cli and pip entry points should not share PATH." >&2
  echo "         Prefer one install method, or adjust PATH / PREFIX." >&2
}

for name in "${NAMES[@]}"; do
  # Only warn for user-facing commands (not the shared launcher filename)
  case "$name" in
    evileye|evileye-launch|evileye-process|evileye-configure|evileye-srv)
      warn_existing "$name"
      ;;
  esac
  install -m 755 "$SRC/$name" "$PREFIX/$name"
done

# Also expose launcher without .sh for convenience if desired — keep .sh as canonical.

case ":$PATH:" in
  *":$PREFIX:"*) ;;
  *)
    echo "warning: $PREFIX is not in PATH. Add it, e.g.:" >&2
    echo "  export PATH=\"$PREFIX:\$PATH\"" >&2
    ;;
esac

echo "Installed EvilEye docker host-cli into $PREFIX"
echo "Image expected: ${EVILEYE_DOCKER_IMAGE:-evileye/app:latest}"
echo "Build if needed: docker compose -f $REPO_ROOT/docker/docker-compose.yml build"
echo "Try: evileye --help"
