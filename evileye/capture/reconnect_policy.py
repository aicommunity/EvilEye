"""Shared reconnect / no-frames anti-flap helpers for capture backends."""

from __future__ import annotations


def allow_noframes_reconnect(
    last_success_ts: float,
    now: float,
    min_interval_sec: float,
) -> bool:
    """Return True when a no-frames reconnect/reset is allowed after a prior success."""
    if last_success_ts <= 0:
        return True
    if min_interval_sec <= 0:
        return True
    return (now - last_success_ts) >= float(min_interval_sec)


def reconnect_wait_sec(
    attempt: int,
    *,
    initial_delay_sec: float,
    backoff_step_sec: float,
    max_delay_sec: float,
    min_first_backoff_sec: float = 0.0,
) -> float:
    """Backoff wait before reconnect attempt ``attempt`` (0-based).

    Attempt 0 is immediate unless ``min_first_backoff_sec`` is set and this is a
    forced non-zero wait for repeated sessions (pass attempt>=1 normally).
    """
    if attempt <= 0:
        return max(0.0, float(min_first_backoff_sec)) if min_first_backoff_sec else 0.0
    wait = float(initial_delay_sec) + (int(attempt) - 1) * float(backoff_step_sec)
    if wait > float(max_delay_sec):
        wait = float(max_delay_sec)
    if min_first_backoff_sec:
        wait = max(wait, float(min_first_backoff_sec))
    return max(0.0, wait)
