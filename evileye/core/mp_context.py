"""Multiprocessing context for EvilEye workers (CUDA-safe spawn)."""

from __future__ import annotations

import multiprocessing as mp

from .resource_tracker_patch import apply_resource_tracker_patch

_SPAWN_CTX: mp.context.BaseContext | None = None


def get_spawn_context() -> mp.context.BaseContext:
    """
    Return a spawn multiprocessing context.

    CUDA/ONNX/PyTorch must not be initialized in the parent before forked children
    start inference. Linux defaults to fork; we force spawn for MpControl workers.
    """
    global _SPAWN_CTX
    if _SPAWN_CTX is not None:
        return _SPAWN_CTX
    try:
        mp.set_start_method("spawn")
    except RuntimeError:
        # Already set (e.g. by Qt configurer or a prior call in this interpreter).
        pass
    _SPAWN_CTX = mp.get_context("spawn")
    return _SPAWN_CTX


def ensure_spawn_start_method() -> None:
    """Call early at app entry before loading GPU models or starting workers."""
    apply_resource_tracker_patch()
    get_spawn_context()
