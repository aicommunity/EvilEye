#!/usr/bin/env bash
# EvilEye docker host-cli
# Shared launcher: run a command inside the EvilEye GPU container with cwd bind-mounted.
set -euo pipefail

EVILEYE_DOCKER_IMAGE="${EVILEYE_DOCKER_IMAGE:-evileye/app:latest}"
EVILEYE_DOCKER_GPU_MODE="${EVILEYE_DOCKER_GPU_MODE:-gpus}" # gpus | cdi | none

if ! command -v docker >/dev/null 2>&1; then
  echo "error: docker not found in PATH" >&2
  exit 127
fi

if ! docker image inspect "$EVILEYE_DOCKER_IMAGE" >/dev/null 2>&1; then
  echo "error: image '$EVILEYE_DOCKER_IMAGE' not found." >&2
  echo "Build it first:" >&2
  echo "  docker compose -f docker/docker-compose.yml build" >&2
  exit 1
fi

if [[ $# -lt 1 ]]; then
  echo "usage: $(basename "$0") <command> [args...]" >&2
  exit 2
fi

DOCKER_ARGS=(
  --rm
  --ipc=host
  -e NVIDIA_VISIBLE_DEVICES="${NVIDIA_VISIBLE_DEVICES:-all}"
  -e NVIDIA_DRIVER_CAPABILITIES="${NVIDIA_DRIVER_CAPABILITIES:-compute,utility,video}"
  -e PYTHONUNBUFFERED=1
  -v "${PWD}:${PWD}"
  -w "${PWD}"
)

# Allocate a TTY only when stdin is a terminal
if [[ -t 0 ]]; then
  DOCKER_ARGS+=(-it)
else
  DOCKER_ARGS+=(-i)
fi

# Optional data-dir env (host path, same path inside container via PWD mount)
if [[ -n "${EVILEYE_DATA_DIR:-}" ]]; then
  DOCKER_ARGS+=(-e "EVILEYE_DATA_DIR=${EVILEYE_DATA_DIR}")
elif [[ -d "${PWD}/EvilEyeData" ]]; then
  DOCKER_ARGS+=(-e "EVILEYE_DATA_DIR=${PWD}/EvilEyeData")
fi

# Mount common project siblings if present outside PWD but under REPO guess — skip;
# cwd layout is the default: run from the deploy directory that contains configs/videos/etc.

case "$EVILEYE_DOCKER_GPU_MODE" in
  gpus)
    DOCKER_ARGS+=(--gpus all)
    ;;
  cdi)
    DOCKER_ARGS+=(--device nvidia.com/gpu=all)
    ;;
  none)
    ;;
  *)
    echo "error: unknown EVILEYE_DOCKER_GPU_MODE='$EVILEYE_DOCKER_GPU_MODE' (gpus|cdi|none)" >&2
    exit 2
    ;;
esac

# shellcheck disable=SC2206
EXTRA=( ${EVILEYE_DOCKER_EXTRA_ARGS:-} )
if [[ ${#EXTRA[@]} -gt 0 ]]; then
  DOCKER_ARGS+=("${EXTRA[@]}")
fi

exec docker run "${DOCKER_ARGS[@]}" "$EVILEYE_DOCKER_IMAGE" "$@"
