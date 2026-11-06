"""Batch processor adapter."""

from __future__ import annotations

from typing import Any

from ..base_class import EvilEyeBase
from ..plugins import ModuleRuntimeContext, PluginError
from .policy import (
    RestartBudget,
    _ERROR_POLICY_PARAMS,
    _HealthMixin,
    _ItemErrorPolicy,
    _ItemErrorTracker,
)
from .transport import _call_factory, _close_item_resources, _create_state


class BatchProcessorModuleAdapter(_HealthMixin, EvilEyeBase):
    """Adapt a synchronous, thread-only ``process_batch`` plugin to a pipeline stage.

    A failing batch is skipped (``error_policy=skip_item``, the default): the stage emits
    nothing for that tick. After ``error_burst_limit`` consecutive failures the module is
    recreated, within the ``max_restarts`` budget; when the budget is spent or the policy
    is ``fail_stop`` the exception propagates and the module is marked failed.
    """

    def __init__(self, registered_module):
        self.registered_module = registered_module
        self.module_id = registered_module.qualified_id
        self.execution_mode = "thread"
        self.source_ids: list[int] = []
        self._config: dict[str, Any] = {}
        self._module = None
        self._state = None
        self._init_kwargs: dict[str, Any] = {}
        self._error_policy = _ItemErrorPolicy()
        self._error_tracker = _ItemErrorTracker(self._error_policy)
        self._restart_budget = RestartBudget(
            self._error_policy.max_restarts, self._error_policy.restart_window_s
        )
        self.item_errors = 0
        self.worker_restarts = 0
        self.degraded = False
        super().__init__()

    def set_params_impl(self):
        params = dict(self.params or {})
        self.module_id = str(params.get("module_id") or params.get("type") or self.module_id)
        self.execution_mode = str(params.get("execution_mode", "thread")).strip().lower()
        if self.execution_mode != "thread":
            raise PluginError(
                f"Batch processor '{self.module_id}' supports thread execution only"
            )
        self.source_ids = [int(item) for item in (params.get("source_ids") or [])]
        self._config = dict(params.get("config") or {})
        reserved = {
            "type", "module_id", "execution_mode", "source_ids", "config", "queue_size", "ipc_mode",
        } | _ERROR_POLICY_PARAMS
        for key, value in params.items():
            if key not in reserved:
                self._config.setdefault(key, value)
        self._error_policy = _ItemErrorPolicy.from_params(params, self.module_id)
        self._error_tracker = _ItemErrorTracker(self._error_policy)
        self._restart_budget = RestartBudget(
            self._error_policy.max_restarts, self._error_policy.restart_window_s
        )
        self._set_degraded_threshold(self._error_policy.degraded_threshold)
        module_params = dict(params)
        module_params.pop("module_id", None)
        module_params.pop("config", None)
        for key in _ERROR_POLICY_PARAMS:
            module_params.pop(key, None)
        module_params.setdefault("type", self.module_id.rsplit("/", 1)[-1])
        self._module_params = module_params
        self._create_module()

    def _create_module(self) -> None:
        self._module = _call_factory(self.registered_module.spec.factory, self._config)
        if not callable(getattr(self._module, "process_batch", None)):
            raise PluginError(
                f"Batch processor '{self.registered_module.qualified_id}' must implement process_batch(batch, state)"
            )
        set_params = getattr(self._module, "set_params", None)
        if callable(set_params):
            set_params(**self._module_params)

    def get_params_impl(self):
        return dict(self.params or {})

    def get_source_ids(self):
        callback = getattr(self._module, "get_source_ids", None)
        if callable(callback):
            return callback()
        return self.source_ids

    def init_impl(self, **kwargs):
        self._init_kwargs = dict(kwargs)
        if self.execution_mode != "thread":
            raise PluginError(
                f"Batch processor '{self.module_id}' supports thread execution only"
            )
        init = getattr(self._module, "init", None)
        if callable(init):
            result = init(**kwargs)
            if result is False:
                return False
        context = ModuleRuntimeContext(
            module_id=self.registered_module.qualified_id,
            execution_mode=self.execution_mode,
            source_ids=tuple(self.source_ids),
        )
        self._state = _create_state(self._module, self._config, context)
        return True

    def process_batch(self, batch):
        try:
            result = self._module.process_batch(batch, self._state)
        except Exception:
            self.item_errors += 1
            self._record_item_error_event()
            action = self._error_tracker.failure()
            if self._error_tracker.consecutive == 1:
                self.logger.exception(
                    "Batch plugin %s failed while processing a batch (policy=%s)",
                    self.module_id, self._error_policy.policy,
                )
            else:
                self.logger.warning(
                    "Batch plugin %s failed again (consecutive=%d, policy=%s)",
                    self.module_id, self._error_tracker.consecutive, self._error_policy.policy,
                )
            if action == "skip":
                return []
            if action == "restart" and self._restart_module():
                return []
            self.degraded = True
            raise
        self._error_tracker.success()
        return result

    def _restart_module(self) -> bool:
        """Recreate the module after repeated failures; False when the budget is spent."""
        policy = self._error_policy
        if not self._restart_budget.try_acquire():
            self.logger.error(
                "Batch plugin %s exhausted its restart budget (%d restarts in %.0fs)",
                self.module_id, policy.max_restarts, policy.restart_window_s,
            )
            return False
        try:
            stop = getattr(self._module, "stop", None)
            if callable(stop):
                stop()
        except Exception:
            self.logger.exception("Batch plugin %s failed to stop before a restart", self.module_id)
        _close_item_resources(self._module, self._state, self.logger, self.module_id)
        self._module = None
        self._state = None
        try:
            self._create_module()
            if self.init_impl(**self._init_kwargs) is False:
                raise PluginError(f"Batch plugin '{self.module_id}' init returned false")
            self.start()
        except Exception:
            self.logger.exception("Batch plugin %s failed to restart", self.module_id)
            return False
        self.worker_restarts += 1
        self._transient_problems.record()
        self._error_tracker.success()
        self.logger.warning(
            "Batch plugin %s restarted after repeated errors (restarts=%d)",
            self.module_id, self.worker_restarts,
        )
        return True

    def get_runtime_stats(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "execution_mode": self.execution_mode,
            "module_initialized": self._module is not None,
            "degraded": self.degraded,
            "error_policy": self._error_policy.policy,
            "item_errors": self.item_errors,
            "worker_restarts": self.worker_restarts,
            **self._health_stats(),
        }

    def start(self):
        callback = getattr(self._module, "start", None)
        if callable(callback):
            callback()

    def stop(self):
        callback = getattr(self._module, "stop", None)
        if callable(callback):
            callback()

    def default(self):
        self.reset_impl()

    def reset_impl(self):
        callback = getattr(self._module, "reset", None)
        if callable(callback):
            callback()
        self.degraded = False
        self.item_errors = 0
        self.worker_restarts = 0
        self._error_tracker = _ItemErrorTracker(self._error_policy)
        self._restart_budget.reset()

    def release_impl(self):
        self.stop()
        _close_item_resources(self._module, self._state, self.logger, self.module_id)
        self._module = None
        self._state = None

    def __getattr__(self, name: str):
        module = self.__dict__.get("_module")
        if module is not None and hasattr(module, name):
            return getattr(module, name)
        raise AttributeError(name)
