from __future__ import annotations

import warnings
from typing import Optional
from .pipeline_manager import PipelineManager
from evileye.core.runtime_services import get_pipeline_manager

"""Compatibility facade for pipeline manager access.

Deprecated: use ``evileye.core.runtime_services.get_pipeline_manager``.
"""

_DEPRECATION_WARNED = False

def get_manager() -> PipelineManager:
    global _DEPRECATION_WARNED
    if not _DEPRECATION_WARNED:
        warnings.warn(
            "evileye.api.core.manager_access.get_manager() is deprecated; "
            "use evileye.core.runtime_services.get_pipeline_manager()",
            DeprecationWarning,
            stacklevel=2,
        )
        _DEPRECATION_WARNED = True
    manager: Optional[PipelineManager] = get_pipeline_manager()
    return manager
