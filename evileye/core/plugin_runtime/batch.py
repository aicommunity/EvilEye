"""Batch processor adapter."""

from __future__ import annotations

from typing import Any

from ..base_class import EvilEyeBase
from ..plugins import ModuleRuntimeContext, PluginError
from .transport import _call_factory, _close_item_resources, _create_state

class BatchProcessorModuleAdapter(EvilEyeBase):
    """Adapt a synchronous, thread-only ``process_batch`` plugin to a pipeline stage."""

    def __init__(self, registered_module):
        self.registered_module = registered_module
        self.module_id = registered_module.qualified_id
        self.execution_mode = "thread"
        self.source_ids: list[int] = []
        self._config: dict[str, Any] = {}
        self._module = None
        self._state = None
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
        reserved = {"type", "module_id", "execution_mode", "source_ids", "config", "queue_size", "ipc_mode"}
        for key, value in params.items():
            if key not in reserved:
                self._config.setdefault(key, value)
        self._module = _call_factory(self.registered_module.spec.factory, self._config)
        if not callable(getattr(self._module, "process_batch", None)):
            raise PluginError(
                f"Batch processor '{self.registered_module.qualified_id}' must implement process_batch(batch, state)"
            )
        module_params = dict(params)
        module_params.pop("module_id", None)
        module_params.pop("config", None)
        module_params.setdefault("type", self.module_id.rsplit("/", 1)[-1])
        set_params = getattr(self._module, "set_params", None)
        if callable(set_params):
            set_params(**module_params)

    def get_params_impl(self):
        return dict(self.params or {})

    def get_source_ids(self):
        callback = getattr(self._module, "get_source_ids", None)
        if callable(callback):
            return callback()
        return self.source_ids

    def init_impl(self, **kwargs):
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
            return self._module.process_batch(batch, self._state)
        except Exception:
            self.degraded = True
            self.logger.exception("Batch plugin %s failed while processing a batch", self.module_id)
            raise

    def get_runtime_stats(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "execution_mode": self.execution_mode,
            "module_initialized": self._module is not None,
            "degraded": self.degraded,
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
