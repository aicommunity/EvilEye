"""Compatibility shim for frame broker access.

Prefer ``evileye.core.runtime_services.get_frame_broker``.
"""

from evileye.core.runtime_services import get_frame_broker as get_broker

__all__ = ["get_broker"]
