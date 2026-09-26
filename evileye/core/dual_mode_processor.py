"""Base helper for components with thread vs process execution_mode.

Reference adoption (S1 / TD-DOC-001): subclass and implement
``_init_thread_mode`` / ``_init_process_mode``. See
``examples/custom_pipeline_stage/`` for a minimal DualMode stage.
"""

from __future__ import annotations

from .base_class import EvilEyeBase
from .processor_base import DEFAULT_EXECUTION_MODE, EXEC_MODE_PROCESS, EXEC_MODE_THREAD


class DualModeProcessor(EvilEyeBase):
    """Dual-mode lifecycle: execution_mode + init_impl branch + optional bridge hooks."""

    def __init__(self):
        super().__init__()
        self.execution_mode: str = DEFAULT_EXECUTION_MODE
        self._mp_control = None
        self._bridge = None

    def set_params_impl(self):
        if self.params:
            self.execution_mode = self.params.get(
                "execution_mode", self.execution_mode
            )

    def init_impl(self, **kwargs):
        if self.execution_mode == EXEC_MODE_PROCESS:
            return self._init_process_mode(**kwargs)
        self.execution_mode = EXEC_MODE_THREAD
        return self._init_thread_mode(**kwargs)

    def _init_thread_mode(self, **kwargs):
        raise NotImplementedError

    def _init_process_mode(self, **kwargs):
        raise NotImplementedError

    def release_impl(self):
        if self._bridge is not None:
            try:
                self._bridge.clear()
            except Exception:
                pass
            self._bridge = None
        if self._mp_control is not None:
            try:
                self._mp_control.stop()
            except Exception:
                pass
            self._mp_control = None
