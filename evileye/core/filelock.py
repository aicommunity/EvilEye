"""Portable exclusive file lock (fcntl on POSIX, msvcrt on Windows)."""

from __future__ import annotations

import os
import sys
import time
import warnings
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional, TextIO, Union

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None  # type: ignore

try:
    import msvcrt
except ImportError:
    msvcrt = None  # type: ignore

_WARNED_NOOP = False


def _warn_noop_once() -> None:
    global _WARNED_NOOP
    if not _WARNED_NOOP:
        warnings.warn(
            "evileye.core.filelock: no platform lock available; proceeding without lock",
            RuntimeWarning,
            stacklevel=3,
        )
        _WARNED_NOOP = True


@contextmanager
def with_file_lock(
    target: Union[Path, str, TextIO],
    *,
    exclusive: bool = True,
) -> Iterator[Optional[TextIO]]:
    """Hold an exclusive lock for the duration of the context.

    If ``target`` is a path, opens a sidecar ``{name}.lock`` file.
    If ``target`` is an open file object, locks that fd (POSIX flock) or a sidecar.
    """
    handle: Optional[TextIO] = None
    owns_handle = False
    lock_path: Optional[Path] = None

    try:
        if hasattr(target, "fileno"):
            # Open file-like
            if fcntl is not None:
                flag = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
                fcntl.flock(target.fileno(), flag)  # type: ignore[union-attr]
                try:
                    yield target  # type: ignore[misc]
                finally:
                    fcntl.flock(target.fileno(), fcntl.LOCK_UN)  # type: ignore[union-attr]
                return
            # Windows: use sidecar next to path if we know it
            name = getattr(target, "name", None)
            if name and msvcrt is not None:
                lock_path = Path(str(name) + ".lock")
            else:
                _warn_noop_once()
                yield target  # type: ignore[misc]
                return
        else:
            lock_path = Path(target)
            if lock_path.suffix != ".lock":
                lock_path = Path(str(lock_path) + ".lock")

        assert lock_path is not None
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "a+", encoding="utf-8")
        owns_handle = True

        if fcntl is not None:
            flag = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            fcntl.flock(handle.fileno(), flag)
            try:
                yield handle
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        elif msvcrt is not None:
            # msvcrt.locking locks byte regions; keep one byte locked
            handle.seek(0)
            if handle.read(1) == "":
                handle.write("0")
                handle.flush()
            handle.seek(0)
            deadline = time.time() + 60.0
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    if time.time() >= deadline:
                        raise
                    time.sleep(0.05)
            try:
                yield handle
            finally:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        else:
            _warn_noop_once()
            yield handle
    finally:
        if owns_handle and handle is not None:
            try:
                handle.close()
            except Exception:
                pass
