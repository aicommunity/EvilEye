#!/usr/bin/env bash
# One-time cleanup for /media/user/Data8/EvilEyeData (run with --execute to delete).
set -euo pipefail

DATA_ROOT="${EVILEYE_DATA_ROOT:-/media/user/Data8/EvilEyeData}"
STREAMS_DAYS="${STREAMS_DAYS:-7}"
IMAGES_RETENTION_DAYS="${IMAGES_RETENTION_DAYS:-180}"
EXECUTE=false

for arg in "$@"; do
    case "$arg" in
        --execute) EXECUTE=true ;;
        --dry-run) EXECUTE=false ;;
        *) echo "Usage: $0 [--dry-run|--execute]"; exit 1 ;;
    esac
done

log() { echo "[$(date -Is)] $*"; }

delete_path() {
    local path="$1"
    local size
    size=$(du -sh "$path" 2>/dev/null | cut -f1 || echo "?")
    if $EXECUTE; then
        log "DELETE $size $path"
        rm -rf "$path"
    else
        log "DRY-RUN would delete $size $path"
    fi
}

log "Data root: $DATA_ROOT (execute=$EXECUTE)"

# Streams older than STREAMS_DAYS
if [[ -d "$DATA_ROOT/Streams" ]]; then
    while IFS= read -r -d '' f; do
        delete_path "$f"
    done < <(find "$DATA_ROOT/Streams" -type f -mtime +"$STREAMS_DAYS" -print0 2>/dev/null || true)
fi

# Legacy images/YYYY_MM_DD directories by retention
if [[ -d "$DATA_ROOT/images" ]]; then
    cutoff_epoch=$(date -d "-${IMAGES_RETENTION_DAYS} days" +%s)
    for date_dir in "$DATA_ROOT/images"/*/; do
        [[ -d "$date_dir" ]] || continue
        name=$(basename "$date_dir")
        if [[ "$name" =~ ^[0-9]{4}_[0-9]{2}_[0-9]{2}$ ]]; then
            dir_epoch=$(date -d "${name//_/-}" +%s 2>/dev/null || echo 0)
            if (( dir_epoch > 0 && dir_epoch < cutoff_epoch )); then
                delete_path "$date_dir"
            fi
        fi
    done
fi

# Event videos older than STREAMS_DAYS
if [[ -d "$DATA_ROOT/Events" ]]; then
    while IFS= read -r -d '' f; do
        delete_path "$f"
    done < <(find "$DATA_ROOT/Events" -path '*/Videos/*' -type f -mtime +"$STREAMS_DAYS" -print0 2>/dev/null || true)
fi

log "Done. Current usage:"
du -sh "$DATA_ROOT" 2>/dev/null || true
