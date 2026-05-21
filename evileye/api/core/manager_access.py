"""Compatibility shim for pipeline manager access.

Prefer ``evileye.core.runtime_services.get_pipeline_manager``.
"""

from evileye.core.runtime_services import get_pipeline_manager as get_manager

__all__ = ["get_manager"]
