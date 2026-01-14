from typing import Optional
from .frame_broker import FrameBroker

""" Module for accessing the frame broker, singleton """

_broker: Optional[FrameBroker] = None


def get_broker() -> FrameBroker:
    global _broker
    if _broker is None:
        _broker = FrameBroker()
    return _broker


