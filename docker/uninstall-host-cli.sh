#!/usr/bin/env bash
# EvilEye docker host-cli
# Remove host-cli wrappers previously installed by install-host-cli.sh.
# Does not touch pip-installed packages.
set -euo pipefail

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

removed=0
for name in "${NAMES[@]}"; do
  target="$PREFIX/$name"
  if [[ -f "$target" ]] && grep -qF "$MARKER" "$target" 2>/dev/null; then
    rm -f "$target"
    echo "removed $target"
    removed=$((removed + 1))
  elif [[ -e "$target" ]]; then
    echo "skip $target (not an EvilEye docker host-cli script)"
  fi
done

echo "Uninstalled $removed host-cli file(s) from $PREFIX"
