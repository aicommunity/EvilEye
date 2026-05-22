"""Base helper for components with thread vs process execution_mode."""

from __future__ import annotations

from .base_class import EvilEyeBase
from .processor_base import DEFAULT_EXECUTION_MODE, EXEC_MODE_PROCESS


class DualModeProcessor(EvilEyeBase):
    """Minimal dual-mode lifecycle: execution_mode + init_impl branch."""

    def __init__(self):
        super().__init__()
        self.execution_mode: str = DEFAULT_EXECUTION_MODE

    def set_params_impl(self):
        if self.params:
            self.execution_mode = self.params.get(
                "execution_mode", self.execution_mode
            )

    def init_impl(self, **kwargs):
        if self.execution_mode == EXEC_MODE_PROCESS:
            return self._init_process_mode(**kwargs)
        return self._init_thread_mode(**kwargs)

    def _init_thread_mode(self, **kwargs):
        raise NotImplementedError

    def _init_process_mode(self, **kwargs):
        raise NotImplementedError
