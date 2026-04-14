from typing import Optional
from .pipeline_manager import PipelineManager
from evileye.core.runtime_context import get_runtime_context, update_runtime_context

""" Module for accessing the pipeline manager, singleton """

_manager: Optional[PipelineManager] = None


def get_manager() -> PipelineManager:
    global _manager
    ctx = get_runtime_context()
    if ctx.manager is not None:
        return ctx.manager
    if _manager is None:
        _manager = PipelineManager()
    update_runtime_context(manager=_manager)
    return _manager
