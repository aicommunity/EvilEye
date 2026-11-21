"""Error policy, restart budget and degraded-state bookkeeping shared by runtime adapters."""

from __future__ import annotations

import time
from typing import Any, Mapping

from ..health_window import RollingEventCounter
from ..plugins import PluginError

_ERROR_POLICIES = ("skip_item", "restart", "fail_stop")


_ERROR_POLICY_PARAMS = frozenset({
    "error_policy", "error_burst_limit", "max_restarts", "restart_window_s",
    "mp_restart_on_exit", "mp_no_restart_exit_codes", "error_degraded_threshold",
})


class _ItemErrorPolicy:
    """How an item module reacts to exceptions raised by ``process_item``.

    ``skip_item`` drops the failing item and escalates to a worker restart after
    ``error_burst_limit`` consecutive failures, ``restart`` recreates the worker
    after every failure and ``fail_stop`` keeps the legacy "stop for good"
    behavior. Restarts are limited to ``max_restarts`` per ``restart_window_s``.
    """

    def __init__(
        self,
        policy: str = "skip_item",
        burst_limit: int = 50,
        max_restarts: int = 5,
        restart_window_s: float = 60.0,
        restart_on_exit: bool | None = None,
        no_restart_exit_codes: Any = None,
        degraded_threshold: int = 5,
    ):
        self.degraded_threshold = degraded_threshold
        self.policy = policy
        self.burst_limit = burst_limit
        self.max_restarts = max_restarts
        self.restart_window_s = restart_window_s
        self.restart_on_exit = (
            policy != "fail_stop" if restart_on_exit is None else bool(restart_on_exit)
        )
        self.no_restart_exit_codes = (
            None if no_restart_exit_codes is None else tuple(sorted(no_restart_exit_codes))
        )

    @classmethod
    def from_params(
        cls, params: Mapping[str, Any], module_id: str, default_policy: str = "skip_item"
    ) -> "_ItemErrorPolicy":
        policy = params.get("error_policy", default_policy)
        if policy not in _ERROR_POLICIES:
            raise PluginError(
                f"Module '{module_id}' error_policy must be one of "
                f"{', '.join(_ERROR_POLICIES)}, got {policy!r}"
            )

        def _number(key, default, kind, minimum):
            value = params.get(key, default)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PluginError(f"Module '{module_id}' {key} must be a number, got {value!r}")
            value = kind(value)
            if value < minimum:
                raise PluginError(f"Module '{module_id}' {key} must be >= {minimum}, got {value!r}")
            return value

        restart_on_exit = params.get("mp_restart_on_exit")
        if restart_on_exit is not None and (
            isinstance(restart_on_exit, bool) is False and restart_on_exit not in (0, 1)
        ):
            raise PluginError(
                f"Module '{module_id}' mp_restart_on_exit must be a boolean, got {restart_on_exit!r}"
            )
        codes = params.get("mp_no_restart_exit_codes")
        if codes is not None:
            raw = codes if isinstance(codes, (list, tuple, set, frozenset)) else [codes]
            if any(isinstance(code, bool) or not isinstance(code, int) for code in raw):
                raise PluginError(
                    f"Module '{module_id}' mp_no_restart_exit_codes must be an integer "
                    f"or a list of integers, got {codes!r}"
                )
            codes = set(raw)
        return cls(
            policy=policy,
            burst_limit=_number("error_burst_limit", 50, int, 1),
            max_restarts=_number("max_restarts", 5, int, 0),
            restart_window_s=_number("restart_window_s", 60.0, float, 0.0),
            restart_on_exit=None if restart_on_exit is None else bool(restart_on_exit),
            no_restart_exit_codes=codes,
            degraded_threshold=_number("error_degraded_threshold", 5, int, 1),
        )

    def to_state(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "burst_limit": self.burst_limit,
            "max_restarts": self.max_restarts,
            "restart_window_s": self.restart_window_s,
            "restart_on_exit": self.restart_on_exit,
            "no_restart_exit_codes": self.no_restart_exit_codes,
            "degraded_threshold": self.degraded_threshold,
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any] | None) -> "_ItemErrorPolicy":
        return cls(**dict(state)) if state else cls()

    def mp_control_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "restart_on_exit": self.restart_on_exit,
            "max_restarts": self.max_restarts,
            "restart_window_s": self.restart_window_s,
        }
        if self.no_restart_exit_codes is not None:
            kwargs["no_restart_exit_codes"] = set(self.no_restart_exit_codes)
        return kwargs


class _ItemErrorTracker:
    """Counts consecutive ``process_item`` failures and picks the reaction."""

    def __init__(self, policy: _ItemErrorPolicy):
        self.policy = policy
        self.consecutive = 0
        self.total = 0

    def success(self) -> None:
        self.consecutive = 0

    def failure(self) -> str:
        """Return ``"skip"``, ``"restart"`` or ``"fail"``."""
        self.total += 1
        self.consecutive += 1
        if self.policy.policy == "fail_stop":
            return "fail"
        if self.policy.policy == "restart" or self.consecutive >= self.policy.burst_limit:
            return "restart"
        return "skip"


class RestartBudget:
    """At most ``max_restarts`` restarts inside a sliding ``window_sec`` window."""

    def __init__(self, max_restarts: int, window_sec: float, clock=time.monotonic):
        self.max_restarts = int(max_restarts)
        self.window_sec = float(window_sec)
        self._clock = clock
        self._times: list[float] = []

    def _prune(self) -> None:
        horizon = self._clock() - self.window_sec
        self._times = [t for t in self._times if t >= horizon]

    def recent(self) -> int:
        self._prune()
        return len(self._times)

    def try_acquire(self) -> bool:
        self._prune()
        if len(self._times) >= self.max_restarts:
            return False
        self._times.append(self._clock())
        return True

    def reset(self) -> None:
        self._times = []


class _HealthCounters:
    def __init__(self, threshold: int = 5):
        self.transient = RollingEventCounter()
        self.item_errors = RollingEventCounter()
        self.threshold = threshold


class _HealthMixin:
    """``degraded`` = permanent failure, recent overload/restarts, or a burst of item errors.

    A single bad item does not turn the module red: ``error_degraded_threshold`` errors
    inside the degraded window (``EVILEYE_DEGRADED_WINDOW_SEC``) are needed.
    """

    _failed = False

    def _health(self) -> _HealthCounters:
        counters = self.__dict__.get("_health_counters")
        if counters is None:
            counters = self.__dict__["_health_counters"] = _HealthCounters()
        return counters

    @property
    def _transient_problems(self) -> RollingEventCounter:
        return self._health().transient

    @property
    def degraded(self) -> bool:
        counters = self._health()
        return (
            self._failed
            or counters.transient.active()
            or counters.item_errors.recent() >= counters.threshold
        )

    @degraded.setter
    def degraded(self, value: bool) -> None:
        self._failed = bool(value)
        if not value:
            counters = self._health()
            counters.transient.reset()
            counters.item_errors.reset()

    def _set_degraded_threshold(self, threshold: int) -> None:
        self._health().threshold = max(1, int(threshold))

    def _record_item_error_event(self) -> None:
        self._health().item_errors.record()

    def _health_stats(self) -> dict[str, Any]:
        counters = self._health()
        return {
            "failed": self._failed,
            "recent_overload_events": counters.transient.recent(),
            "recent_item_errors": counters.item_errors.recent(),
            "degraded_error_threshold": counters.threshold,
            "degraded_window_sec": counters.transient.window_sec,
        }
