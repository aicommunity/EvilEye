"""Process resource statistics via psutil."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class ProcessResourceStats:
    pid: Optional[int]
    rss_mb: Optional[float]
    num_threads: Optional[int]
    num_fds: Optional[int]
    open_files: Optional[int]


def collect_process_resource_stats(pid: Optional[int] = None) -> Optional[ProcessResourceStats]:
    """Collect RSS, thread count, and FD metrics for a process."""
    try:
        import psutil  # type: ignore
    except ImportError:
        return None

    try:
        resolved_pid = pid if pid is not None else os.getpid()
        proc = psutil.Process(resolved_pid)
        mem = proc.memory_info()
        rss_mb = mem.rss / (1024 * 1024)
        num_threads = None
        num_fds = None
        open_files = None
        try:
            num_threads = proc.num_threads()
        except Exception:
            pass
        try:
            num_fds = proc.num_fds()
        except Exception:
            pass
        try:
            open_files = len(proc.open_files())
        except Exception:
            pass
        return ProcessResourceStats(
            pid=resolved_pid,
            rss_mb=rss_mb,
            num_threads=num_threads,
            num_fds=num_fds,
            open_files=open_files,
        )
    except Exception:
        return None


def format_resource_stats_line(
        context: str,
        stats: ProcessResourceStats,
        extra_suffix: str = "",
) -> str:
    """Format a single log line for resource stats."""
    rss = stats.rss_mb
    rss_s = f"{rss:.3f}" if isinstance(rss, (int, float)) else "n/a"
    return (
        f"ResourceStats[{context}] pid={stats.pid} rss_mb={rss_s} "
        f"threads={stats.num_threads if stats.num_threads is not None else 'n/a'} "
        f"fds={stats.num_fds if stats.num_fds is not None else 'n/a'} "
        f"open_files={stats.open_files if stats.open_files is not None else 'n/a'}"
        f"{extra_suffix}"
    )
