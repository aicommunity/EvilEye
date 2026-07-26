"""CUDA / GPU error detection helpers for multiprocessing workers."""

from __future__ import annotations

import re
from typing import Any

# Dedicated process exit code: MpControl must not auto-restart on this code.
MP_EXIT_CUDA_OOM = 42

_CUDA_OOM_PATTERNS = (
    re.compile(r"cuda.*out of memory", re.IGNORECASE),
    re.compile(r"out of memory.*cuda", re.IGNORECASE),
    re.compile(r"cudart.*out of memory", re.IGNORECASE),
    re.compile(r"cuda error:\s*out of memory", re.IGNORECASE),
)


class CudaOutOfMemoryError(RuntimeError):
    """Raised when a CUDA OOM condition is detected."""


def is_cuda_oom_error(exc: BaseException | None) -> bool:
    """Return True if *exc* (or its cause chain) looks like CUDA OOM."""
    if exc is None:
        return False
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = str(current)
        for pattern in _CUDA_OOM_PATTERNS:
            if pattern.search(text):
                return True
        current = current.__cause__ or current.__context__
    return False


def format_cuda_oom_message(
    *,
    component: str,
    detail: str = "",
    extra: dict[str, Any] | None = None,
) -> str:
    parts = [f"CUDA out of memory in {component}"]
    if detail:
        parts.append(detail)
    if extra:
        for key, value in extra.items():
            parts.append(f"{key}={value}")
    return "; ".join(parts)


def cuda_memory_snapshot() -> str:
    """Best-effort CUDA memory stats for diagnostic logs."""
    try:
        import torch

        if not torch.cuda.is_available():
            return "cuda_unavailable"
        device = torch.cuda.current_device()
        allocated = torch.cuda.memory_allocated(device)
        reserved = torch.cuda.memory_reserved(device)
        total = torch.cuda.get_device_properties(device).total_memory
        return (
            f"device={device} name={torch.cuda.get_device_name(device)} "
            f"allocated_mb={allocated / (1024 * 1024):.1f} "
            f"reserved_mb={reserved / (1024 * 1024):.1f} "
            f"total_mb={total / (1024 * 1024):.1f}"
        )
    except Exception as exc:
        return f"snapshot_failed={exc}"
