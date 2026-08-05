"""Path confinement helpers for config and media APIs."""
from __future__ import annotations

import os
from pathlib import Path


class UnsafePathError(ValueError):
    """Raised when a path escapes the allowed base directory or is malformed."""


def safe_basename(name: str, *, require_suffix: str | None = None) -> str:
    """Return a basename-only filename; reject traversal and empty names."""
    raw = str(name or "").strip()
    if not raw or raw in {".", ".."} or "/" in raw or "\\" in raw or ".." in raw:
        raise UnsafePathError(f"Invalid path name: {name!r}")
    safe = Path(raw).name
    if safe != raw or safe in {".", ".."} or ".." in safe:
        raise UnsafePathError(f"Invalid path name: {name!r}")
    if require_suffix and not safe.endswith(require_suffix):
        raise UnsafePathError(f"Name must end with {require_suffix}")
    return safe


def safe_config_name(name: str) -> str:
    return safe_basename(name, require_suffix=".json")


def assert_under_dir(candidate: Path | str, base: Path | str) -> Path:
    """Resolve candidate and ensure it stays under base (symlink-safe)."""
    base_resolved = Path(base).resolve()
    resolved = Path(candidate).resolve()
    try:
        resolved.relative_to(base_resolved)
    except ValueError as exc:
        raise UnsafePathError(f"Path outside allowed directory: {candidate}") from exc
    if not (
        str(resolved).startswith(str(base_resolved) + os.sep) or resolved == base_resolved
    ):
        raise UnsafePathError(f"Path outside allowed directory: {candidate}")
    return resolved


def resolve_under_dir(base: Path | str, *parts: str) -> Path:
    base_path = Path(base)
    return assert_under_dir(base_path.joinpath(*parts), base_path)
