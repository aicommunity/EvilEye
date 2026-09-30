"""Memory attribution helpers for main-process leak diagnosis."""

from __future__ import annotations

import gc
import os
import resource
from typing import Any, Optional


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def process_rss_bytes() -> Optional[int]:
    try:
        # Linux: ru_maxrss is KB
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
    except Exception:
        return None


def collect_memory_attribution(controller: Any) -> dict[str, Any]:
    """Aggregate memory-related counters from controller subsystems."""
    out: dict[str, Any] = {
        "pid": os.getpid(),
        "rss_bytes": None,
        "objects_handler": None,
        "event_buffers": {},
        "event_buffers_total_bytes": 0,
        "gc": None,
        "tracemalloc": None,
    }
    try:
        with open(f"/proc/{os.getpid()}/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    out["rss_bytes"] = int(line.split()[1]) * 1024
                    break
                if line.startswith("RssAnon:"):
                    out.setdefault("rss_anon_bytes", int(line.split()[1]) * 1024)
    except Exception:
        out["rss_bytes"] = process_rss_bytes()

    handler = getattr(controller, "obj_handler", None)
    if handler is not None and hasattr(handler, "get_runtime_stats"):
        try:
            out["objects_handler"] = handler.get_runtime_stats()
        except Exception as exc:
            out["objects_handler"] = {"error": str(exc)}

    buffers = getattr(controller, "event_buffers", None) or {}
    total_bytes = 0
    buf_stats: dict[str, Any] = {}
    for sid, buf in buffers.items():
        try:
            stats = buf.get_runtime_stats() if hasattr(buf, "get_runtime_stats") else {}
        except Exception as exc:
            stats = {"error": str(exc)}
        buf_stats[str(sid)] = stats
        try:
            total_bytes += int(stats.get("estimated_bytes") or 0)
        except Exception:
            pass
    out["event_buffers"] = buf_stats
    out["event_buffers_total_bytes"] = total_bytes

    try:
        out["gc"] = {
            "counts": list(gc.get_count()),
            "garbage": len(gc.garbage),
            "stats": gc.get_stats() if hasattr(gc, "get_stats") else None,
        }
    except Exception:
        pass

    if _env_flag("EVILEYE_TRACEMALLOC"):
        out["tracemalloc"] = _tracemalloc_top(limit=20)
    return out


def ensure_tracemalloc_started() -> bool:
    if not _env_flag("EVILEYE_TRACEMALLOC"):
        return False
    try:
        import tracemalloc

        if not tracemalloc.is_tracing():
            tracemalloc.start(25)
        return True
    except Exception:
        return False


def _tracemalloc_top(limit: int = 20) -> Optional[dict[str, Any]]:
    try:
        import tracemalloc

        if not tracemalloc.is_tracing():
            tracemalloc.start(25)
        snapshot = tracemalloc.take_snapshot()
        stats = snapshot.statistics("lineno")[: max(1, int(limit))]
        current, peak = tracemalloc.get_traced_memory()
        return {
            "current_bytes": int(current),
            "peak_bytes": int(peak),
            "top": [
                {
                    "file": str(s.traceback[0].filename) if s.traceback else "?",
                    "line": int(s.traceback[0].lineno) if s.traceback else 0,
                    "size_bytes": int(s.size),
                    "count": int(s.count),
                }
                for s in stats
            ],
        }
    except Exception as exc:
        return {"error": str(exc)}


def format_memory_attribution_line(attrs: dict[str, Any]) -> str:
    rss = attrs.get("rss_bytes")
    rss_mb = f"{rss / (1024 * 1024):.1f}" if isinstance(rss, int) else "?"
    oh = attrs.get("objects_handler") or {}
    eb = attrs.get("event_buffers_total_bytes") or 0
    return (
        f"MemoryAttr pid={attrs.get('pid')} rss_mb={rss_mb} "
        f"event_buf_mb={float(eb) / (1024 * 1024):.1f} "
        f"active={oh.get('active_objects')} lost={oh.get('lost_objects')} "
        f"hist={oh.get('history_items')} "
        f"last_img_mb={(oh.get('active_last_image_bytes') or 0) / (1024 * 1024):.1f} "
        f"sticky={oh.get('zone_sticky_count')} "
        f"sticky_jpeg_kb={(oh.get('zone_sticky_jpeg_bytes') or 0) / 1024:.1f}"
    )
