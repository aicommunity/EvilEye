"""
GUI mode definitions and determination logic.
"""

from enum import Enum
from typing import Optional


class GUIMode(Enum):
    """GUI operation modes."""
    HEADLESS = "headless"  # No GUI, no Qt components
    HIDDEN = "hidden"  # Qt app created but windows hidden until activation
    VISIBLE = "visible"  # Windows shown immediately


def determine_gui_mode(config: dict, cli_gui: Optional[bool] = None) -> GUIMode:
    """
    Determine GUI mode from config and CLI arguments.
    
    Args:
        config: Configuration dictionary
        cli_gui: CLI argument for GUI (True/False/None)
        
    Returns:
        GUIMode enum value
        
    Priority:
    1. CLI argument (if provided)
    2. Config controller.gui_mode
    3. Config controller.gui_enabled and controller.show_main_gui
    4. Default: VISIBLE
    """
    controller_config = config.get("controller", {})
    
    # Priority 1: CLI argument
    if cli_gui is not None:
        if not cli_gui:
            return GUIMode.HEADLESS
        # If CLI says GUI enabled, check for hidden mode in config
        gui_mode_str = controller_config.get("gui_mode")
        if gui_mode_str == "hidden":
            return GUIMode.HIDDEN
        return GUIMode.VISIBLE
    
    # Priority 2: Explicit gui_mode in config
    gui_mode_str = controller_config.get("gui_mode")
    if gui_mode_str:
        try:
            return GUIMode(gui_mode_str.lower())
        except ValueError:
            pass
    
    # Priority 3: Legacy config (gui_enabled + show_main_gui)
    gui_enabled = controller_config.get("gui_enabled", True)
    if not gui_enabled:
        return GUIMode.HEADLESS
    
    show_main_gui = controller_config.get("show_main_gui", True)
    if not show_main_gui:
        return GUIMode.HIDDEN
    
    # Default: visible GUI
    return GUIMode.VISIBLE
