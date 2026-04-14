from __future__ import annotations

import warnings
from typing import Optional
from .frame_broker import FrameBroker
from evileye.core.runtime_services import get_frame_broker

"""Compatibility facade for frame broker access.

Deprecated: use ``evileye.core.runtime_services.get_frame_broker``.
"""

_DEPRECATION_WARNED = False

def get_broker() -> FrameBroker:
    global _DEPRECATION_WARNED
    if not _DEPRECATION_WARNED:
        warnings.warn(
            "evileye.api.core.broker_access.get_broker() is deprecated; "
            "use evileye.core.runtime_services.get_frame_broker()",
            DeprecationWarning,
            stacklevel=2,
        )
        _DEPRECATION_WARNED = True
    broker: Optional[FrameBroker] = get_frame_broker()
    return broker


