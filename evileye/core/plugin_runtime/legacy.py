"""Adapter for legacy processors that implement the old processor protocol."""

from __future__ import annotations

from ..base_class import EvilEyeBase
from ..plugins import PluginError
from .transport import _call_factory

class LegacyProcessorModuleAdapter(EvilEyeBase):
    """Expose an existing queue/lifecycle processor through the module SPI.

    This bridge lets established model, tracker, and attribute implementations
    keep their proven worker internals while pipelines resolve them through the
    same namespaced registry used by external modules.
    """

    def __init__(self, registered_module):
        self.registered_module = registered_module
        self.module_id = registered_module.qualified_id
        self.execution_mode = "thread"
        self.source_ids = []
        self._module = None
        super().__init__()
        self.ResultType = getattr(registered_module.spec.factory, "ResultType", None)
        self._module = _call_factory(registered_module.spec.factory, {})

    def set_id(self, id_value: int):
        super().set_id(id_value)
        if self._module is not None and callable(getattr(self._module, "set_id", None)):
            self._module.set_id(id_value)

    def set_params_impl(self):
        params = dict(self.params or {})
        self.module_id = str(params.get("module_id") or params.get("type") or self.module_id)
        supported_modes = tuple(self.registered_module.spec.execution_modes)
        default_mode = self.registered_module.spec.default_execution_mode
        if default_mode is None:
            default_mode = "process" if "process" in supported_modes else supported_modes[0]
        self.execution_mode = str(params.get("execution_mode", default_mode)).lower()
        self.source_ids = list(params.get("source_ids") or [])
        module_params = dict(params)
        module_params.pop("module_id", None)
        module_params.setdefault("type", self.module_id.rsplit("/", 1)[-1])
        self._module.set_params(**module_params)
        if callable(getattr(self._module, "set_id", None)):
            self._module.set_id(self.id)

    def get_params_impl(self):
        return self._module.get_params()

    def init_impl(self, **kwargs):
        if self.execution_mode not in self.registered_module.spec.execution_modes:
            raise PluginError(
                f"Module '{self.module_id}' does not support execution_mode="
                f"'{self.execution_mode}'"
            )
        initialized = self._module.init(**kwargs)
        if initialized is None:
            return bool(self._module.get_init_flag())
        return bool(initialized)

    def start(self):
        return self._module.start()

    def stop(self):
        return self._module.stop()

    def put(self, item, *args, **kwargs):
        return self._module.put(item, *args, **kwargs)

    def get(self, *args, **kwargs):
        return self._module.get(*args, **kwargs)

    def get_source_ids(self):
        callback = getattr(self._module, "get_source_ids", None)
        if callable(callback):
            return callback()
        return self.source_ids

    def get_dropped_ids(self):
        callback = getattr(self._module, "get_dropped_ids", None)
        return callback() if callable(callback) else []

    def set_class_manager(self, class_manager):
        callback = getattr(self._module, "set_class_manager", None)
        if callable(callback):
            callback(class_manager)

    def set_system_event_callback(self, callback):
        handler = getattr(self._module, "set_system_event_callback", None)
        if callable(handler):
            handler(callback)

    def get_debug_info(self, debug_info: dict | None):
        callback = getattr(self._module, "get_debug_info", None)
        if callable(callback):
            callback(debug_info if debug_info is not None else {})
        else:
            super().get_debug_info(debug_info)

    def calc_memory_consumption(self):
        callback = getattr(self._module, "calc_memory_consumption", None)
        if callable(callback):
            callback()
            self.memory_measure_results = getattr(self._module, "memory_measure_results", None)
            self.memory_measure_time = getattr(self._module, "memory_measure_time", None)
        else:
            super().calc_memory_consumption()

    def release_impl(self):
        if self._module is not None:
            self._module.release()

    def reset_impl(self):
        if self._module is not None:
            self._module.reset()

    def default(self):
        if self._module is not None:
            self._module.default()

    def __getattr__(self, name: str):
        module = self.__dict__.get("_module")
        if module is not None and hasattr(module, name):
            return getattr(module, name)
        raise AttributeError(name)
