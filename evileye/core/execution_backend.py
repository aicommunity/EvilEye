"""Factory for thread vs process execution backends (S5)."""

from __future__ import annotations

from typing import Callable, TypeVar

from .processor_base import EXEC_MODE_PROCESS

T = TypeVar("T")


def create_execution_backend(
    execution_mode: str,
    *,
    thread_factory: Callable[[], T],
    process_factory: Callable[[], T],
) -> T:
    """Return process or thread backend without getattr duck typing."""
    if execution_mode == EXEC_MODE_PROCESS:
        return process_factory()
    return thread_factory()
