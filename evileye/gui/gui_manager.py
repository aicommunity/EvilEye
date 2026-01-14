"""
GUI Manager for EvilEye application.

Manages GUI components lifecycle and separates core initialization from GUI initialization.
"""

import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any
import logging

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer, QThread, pyqtSignal, QObject
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QTimer, QThread, pyqtSignal, QObject
    pyqt_version = 5

from .gui_mode import GUIMode
from .interfaces import IVisualizationProvider, IProgressReporter
from ..core.logger import get_module_logger


class GUIManager(QObject):
    """Manages GUI components and their lifecycle."""
    
    # Signals for GUI events
    gui_ready = pyqtSignal()  # Emitted when GUI is ready
    gui_shown = pyqtSignal()  # Emitted when GUI is shown
    gui_hidden = pyqtSignal()  # Emitted when GUI is hidden
    
    def __init__(self, mode: GUIMode, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize GUI Manager.
        
        Args:
            mode: GUI operation mode
            config: Configuration dictionary
            logger: Optional logger instance
        """
        super().__init__()
        # Initialize all long-lived variables in constructor
        self.mode = mode
        self.config = config
        self.logger = logger or get_module_logger("gui_manager")
        
        self.qt_app: Optional[QApplication] = None
        self.main_window = None
        self.visualization_adapter = None
        self.progress_reporter = None
        
        # Flag monitoring for hidden GUI mode
        self.flag_monitor_timer: Optional[QTimer] = None
        # GUI activation flag file path - initialize in constructor
        flag_file_config = config.get("controller", {}).get("gui_flag_file", "EvilEyeData/.show_gui")
        self.flag_file_path: Optional[Path] = Path(flag_file_config)
        
    def create_gui_application(self) -> QApplication:
        """
        Create QApplication instance.
        
        Returns:
            QApplication instance
        """
        if self.qt_app is not None:
            return self.qt_app
            
        self.logger.info("Creating QApplication...")
        # Mitigate Qt↔GLib dispatcher conflicts
        try:
            os.environ.setdefault("QT_NO_GLIB", "1")
        except Exception:
            pass
            
        self.qt_app = QApplication.instance() or QApplication(sys.argv)
        self.logger.info("QApplication created")
        return self.qt_app
    
    def initialize(self, controller) -> None:
        """
        Initialize GUI components based on mode.
        
        Args:
            controller: Controller instance
        """
        if self.mode == GUIMode.HEADLESS:
            self.logger.info("Headless mode: skipping GUI initialization")
            return
        
        # Create QApplication
        self.create_gui_application()
        
        if self.mode == GUIMode.HIDDEN:
            self.logger.info("Hidden GUI mode: creating GUI components but not showing")
            self._create_gui_components(controller)
            self._start_flag_monitor()
        elif self.mode == GUIMode.VISIBLE:
            self.logger.info("Visible GUI mode: creating and showing GUI components")
            self._create_gui_components(controller)
            self.show_gui()
    
    def _create_gui_components(self, controller) -> None:
        """
        Create GUI components asynchronously.
        
        Args:
            controller: Controller instance
        """
        # GUI components are created in _connect_gui_to_controller()
        # This method is kept for future use if needed
        self.logger.info("GUI components will be created when connecting to controller")
        pass
    
    def show_gui(self) -> None:
        """Show GUI windows."""
        if self.main_window:
            self.main_window.show()
            self.main_window.raise_()
            self.main_window.activateWindow()
            self.gui_shown.emit()
            self.logger.info("GUI shown")
    
    def hide_gui(self) -> None:
        """Hide GUI windows."""
        if self.main_window:
            self.main_window.hide()
            self.gui_hidden.emit()
            self.logger.info("GUI hidden")
    
    def _start_flag_monitor(self) -> None:
        """Start monitoring file flag for GUI activation."""
        if self.flag_monitor_timer is not None:
            return
            
        self.logger.info(f"Starting flag monitor for file: {self.flag_file_path}")
        self.flag_monitor_timer = QTimer()
        self.flag_monitor_timer.timeout.connect(self._check_gui_activation_flag)
        self.flag_monitor_timer.start(1000)  # Check every second
    
    def _check_gui_activation_flag(self) -> None:
        """Check if GUI activation flag file exists."""
        if self.flag_file_path and self.flag_file_path.exists():
            self.logger.info("GUI activation flag detected, showing GUI")
            self.show_gui()
            # Remove flag file after activation
            try:
                self.flag_file_path.unlink()
            except Exception as e:
                self.logger.warning(f"Failed to remove flag file: {e}")
    
    def set_progress_reporter(self, reporter: IProgressReporter) -> None:
        """Set progress reporter."""
        self.progress_reporter = reporter
    
    def set_visualization_adapter(self, adapter: IVisualizationProvider) -> None:
        """Set visualization adapter."""
        self.visualization_adapter = adapter
    
    def get_qt_application(self) -> Optional[QApplication]:
        """Get QApplication instance."""
        return self.qt_app
    
    def cleanup(self) -> None:
        """Cleanup GUI resources."""
        if self.flag_monitor_timer:
            self.flag_monitor_timer.stop()
            self.flag_monitor_timer = None
        
        if self.main_window:
            try:
                self.main_window.close()
            except Exception:
                pass
            self.main_window = None
