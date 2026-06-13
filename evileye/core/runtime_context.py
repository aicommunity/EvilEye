from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class RuntimeContext:
    """Runtime-scoped service container."""

    broker: Optional[Any] = None
    manager: Optional[Any] = None
    process_manager: Optional[Any] = None


_context = RuntimeContext()
_lock = threading.Lock()


def get_runtime_context() -> RuntimeContext:
    return _context


def update_runtime_context(**kwargs) -> RuntimeContext:
    with _lock:
        for key, value in kwargs.items():
            if hasattr(_context, key):
                setattr(_context, key, value)
    return _context


def reset_runtime_context() -> None:
    with _lock:
        _context.broker = None
        _context.manager = None
        _context.process_manager = None


def get_runtime_service(name: str) -> Optional[Any]:
    """Read runtime service by attribute name."""
    with _lock:
        return getattr(_context, name, None)


def set_runtime_service(name: str, value: Any) -> RuntimeContext:
    """Set runtime service by attribute name if it exists."""
    with _lock:
        if hasattr(_context, name):
            setattr(_context, name, value)
    return _context


def get_or_create_runtime_service(name: str, factory) -> Any:
    """Get runtime service, creating it lazily via factory."""
    with _lock:
        existing = getattr(_context, name, None)
        if existing is not None:
            return existing
        created = factory()
        if hasattr(_context, name):
            setattr(_context, name, created)
        return created
