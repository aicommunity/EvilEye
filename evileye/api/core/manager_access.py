from typing import Optional
from .pipeline_manager import PipelineManager

""" Module for accessing the pipeline manager, singleton """

_manager: Optional[PipelineManager] = None


def get_manager() -> PipelineManager:
    global _manager
    if _manager is None:
        _manager = PipelineManager()
    return _manager
