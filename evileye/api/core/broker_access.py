from typing import Optional
from .frame_broker import FrameBroker
from evileye.core.runtime_context import get_runtime_context, update_runtime_context

""" Module for accessing the frame broker, singleton """

_broker: Optional[FrameBroker] = None


def get_broker() -> FrameBroker:
    global _broker
    ctx = get_runtime_context()
    if ctx.broker is not None:
        return ctx.broker
    if _broker is None:
        _broker = FrameBroker()
    update_runtime_context(broker=_broker)
    return _broker


