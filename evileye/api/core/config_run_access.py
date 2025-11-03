from typing import Optional
from .config_run_manager import ConfigRunManager

_manager: Optional[ConfigRunManager] = None


def get_config_run_manager() -> ConfigRunManager:
    global _manager
    if _manager is None:
        _manager = ConfigRunManager()
    return _manager


