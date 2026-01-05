"""
GUI management module for EvilEye.

This module provides GUI management functionality, separating core initialization
from GUI initialization and supporting multiple GUI modes: headless, hidden, and visible.
"""

from .gui_mode import GUIMode, determine_gui_mode
from .interfaces import IVisualizationProvider, IProgressReporter, IGUIEventHandler
from .gui_manager import GUIManager
from .visualization_adapter import VisualizationAdapter

__all__ = [
    'GUIMode',
    'determine_gui_mode',
    'IVisualizationProvider',
    'IProgressReporter',
    'IGUIEventHandler',
    'GUIManager',
    'VisualizationAdapter',
]
