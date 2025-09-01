#!/usr/bin/env python3
"""
EvilEye Graphical User Interface

Provides a graphical interface for the EvilEye surveillance system.
"""

import sys
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QFileDialog, QTextEdit, QComboBox,
        QGroupBox, QGridLayout, QMessageBox, QProgressBar, QTabWidget
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
    from PyQt6.QtGui import QFont, QIcon
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

from evileye.controller import controller
from evileye.visualization_modules.main_window import MainWindow
from evileye.utils.utils import normalize_config_path


class ConfigLauncher:
    """Configuration launcher that uses launch_main_app approach"""
    
    def __init__(self, config_file_path: str):
        self.config_file_path = normalize_config_path(config_file_path)
        self.process = None
        
    def launch(self):
        """Launch the configuration using process.py"""
        import subprocess
        import sys
        from pathlib import Path
        
        # Get the project root directory (where process.py is located)
        project_root = Path(__file__).parent.parent
        
        # Launch the main process.py with the config
        process_script = project_root / "evileye" / "process.py"
        
        if not process_script.exists():
            # Try alternative locations
            alt_locations = [
                project_root / "process.py",
                Path.cwd() / "process.py",
                Path.cwd() / "evileye" / "process.py"
            ]
            
            for alt_path in alt_locations:
                if alt_path.exists():
                    process_script = alt_path
                    break
            else:
                raise FileNotFoundError(f"process.py not found. Tried: {process_script}, {alt_locations}")
        
        # Build command
        cmd = [sys.executable, str(process_script), "--config", self.config_file_path, "--gui"]
        
        try:
            # Launch in background
            print(f"Launching command: {' '.join(cmd)}")
            print(f"Working directory: {project_root}")
            self.process = subprocess.Popen(cmd, cwd=project_root)
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to launch process: {e}")
    
    def stop(self):
        """Stop the launched process"""
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None
    
    def is_running(self):
        """Check if the process is still running"""
        if self.process is None:
            return False
        return self.process.poll() is None
    
    def get_return_code(self):
        """Get the return code of the process (None if still running)"""
        if self.process is None:
            return None
        return self.process.poll()


class EvilEyeGUI(QMainWindow):
    """Main GUI window for EvilEye"""
    
    def __init__(self):
        super().__init__()
        self.launcher: Optional[ConfigLauncher] = None
        self.config_file_path: str = ""
        self.process_monitor_timer = QTimer()
        self.process_monitor_timer.timeout.connect(self.check_process_status)
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("EvilEye - Configuration Launcher")
        self.setGeometry(100, 100, 800, 600)
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create main layout
        layout = QVBoxLayout(central_widget)
        
        # Create tab widget
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        # Main tab
        main_tab = self.create_main_tab()
        tabs.addTab(main_tab, "Main")
        
        # Configuration tab
        config_tab = self.create_config_tab()
        tabs.addTab(config_tab, "Configuration")
        
        # Logs tab
        logs_tab = self.create_logs_tab()
        tabs.addTab(logs_tab, "Logs")
        
        # Status bar
        self.statusBar().showMessage("Ready")
        
        # Handle window close event
        self.closeEvent = self.on_close_event
        
    def create_main_tab(self) -> QWidget:
        """Create the main tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Title
        title = QLabel("EvilEye Configuration Launcher")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Description
        desc = QLabel("Select a configuration file and launch the system using process.py")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)
        
        # Configuration group
        config_group = QGroupBox("Configuration")
        config_layout = QGridLayout(config_group)
        
        self.config_path_label = QLabel("No configuration selected")
        config_layout.addWidget(QLabel("Config File:"), 0, 0)
        config_layout.addWidget(self.config_path_label, 0, 1)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_config)
        config_layout.addWidget(browse_btn, 0, 2)
        
        layout.addWidget(config_group)
        
        # Control group
        control_group = QGroupBox("Process Controls")
        control_layout = QHBoxLayout(control_group)
        
        self.start_btn = QPushButton("Launch Process")
        self.start_btn.clicked.connect(self.start_pipeline)
        self.start_btn.setEnabled(False)
        control_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("Stop Process")
        self.stop_btn.clicked.connect(self.stop_pipeline)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn)
        
        layout.addWidget(control_group)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Status
        self.status_label = QLabel("Status: Ready")
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        return widget
    
    def create_config_tab(self) -> QWidget:
        """Create the configuration tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Configuration editor
        self.config_editor = QTextEdit()
        self.config_editor.setPlaceholderText("Paste your JSON configuration here...")
        layout.addWidget(self.config_editor)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        load_btn = QPushButton("Load from File")
        load_btn.clicked.connect(self.load_config_file)
        button_layout.addWidget(load_btn)
        
        save_btn = QPushButton("Save to File")
        save_btn.clicked.connect(self.save_config_file)
        button_layout.addWidget(save_btn)
        
        validate_btn = QPushButton("Validate")
        validate_btn.clicked.connect(self.validate_config)
        button_layout.addWidget(validate_btn)
        
        layout.addLayout(button_layout)
        
        return widget
    
    def create_logs_tab(self) -> QWidget:
        """Create the logs tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        layout.addWidget(self.log_display)
        
        # Clear button
        clear_btn = QPushButton("Clear Logs")
        clear_btn.clicked.connect(self.clear_logs)
        layout.addWidget(clear_btn)
        
        return widget
    
    def browse_config(self):
        """Browse for configuration file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Configuration File",
            "configs",
            "JSON Files (*.json)"
        )
        
        if file_path:
            self.config_path_label.setText(file_path)
            self.load_config(file_path)
            self.start_btn.setEnabled(True)
    
    def load_config(self, file_path: str):
        """Load configuration from file"""
        try:
            # Normalize config path
            normalized_path = normalize_config_path(file_path)
            
            with open(normalized_path, 'r') as f:
                config = json.load(f)
            
            # Update config editor
            self.config_editor.setPlainText(json.dumps(config, indent=2))
            
            # Store current config and file path
            self.current_config = config
            self.config_file_path = normalized_path
            
            self.log_message(f"Loaded configuration from {normalized_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load configuration: {e}")
    
    def load_config_file(self):
        """Load configuration from file dialog"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Configuration File",
            "configs",
            "JSON Files (*.json)"
        )
        
        if file_path:
            self.load_config(file_path)
    
    def save_config_file(self):
        """Save configuration to file"""
        try:
            config_text = self.config_editor.toPlainText()
            config = json.loads(config_text)
            
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Configuration File",
                "configs",
                "JSON Files (*.json)"
            )
            
            if file_path:
                with open(file_path, 'w') as f:
                    json.dump(config, f, indent=2)
                
                self.log_message(f"Configuration saved to {file_path}")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save configuration: {e}")
    
    def validate_config(self):
        """Validate current configuration"""
        try:
            config_text = self.config_editor.toPlainText()
            config = json.loads(config_text)
            
            # Basic validation
            if "pipeline" not in config:
                raise ValueError("Missing 'pipeline' section")
            
            pipeline_config = config.get("pipeline", {})
            if "sources" not in pipeline_config:
                raise ValueError("Missing 'sources' section in pipeline")
            
            sources = pipeline_config.get("sources", [])
            if not sources:
                raise ValueError("At least one source must be configured")
            
            QMessageBox.information(self, "Success", "Configuration is valid!")
            self.log_message("Configuration validation successful")
            
        except Exception as e:
            QMessageBox.critical(self, "Validation Error", f"Configuration is invalid: {e}")
            self.log_message(f"Configuration validation failed: {e}")
    
    def start_pipeline(self):
        """Launch the configuration using process.py"""
        try:
            # Ensure we have a config file path
            if not self.config_file_path:
                QMessageBox.warning(self, "Warning", "Please select a configuration file first")
                return
            
            # Save current config to file if it was edited
            config_text = self.config_editor.toPlainText()
            if config_text.strip():
                try:
                    config = json.loads(config_text)
                    with open(self.config_file_path, 'w') as f:
                        json.dump(config, f, indent=2)
                    self.log_message(f"Configuration saved to {self.config_file_path}")
                except Exception as e:
                    QMessageBox.warning(self, "Warning", f"Failed to save configuration: {e}")
            
            # Create and start launcher
            self.launcher = ConfigLauncher(self.config_file_path)
            self.launcher.launch()
            
            # Start monitoring the process
            self.process_monitor_timer.start(1000)  # Check every second
            
            # Update UI
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)  # Indeterminate progress
            
            self.log_message(f"Launched configuration: {self.config_file_path}")
            self.status_label.setText("Status: Running")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to launch configuration: {e}")
            self.log_message(f"Launch error: {e}")
    
    def stop_pipeline(self):
        """Stop the launched process"""
        if self.launcher:
            self.launcher.stop()
            self.launcher = None
            
        # Stop monitoring
        self.process_monitor_timer.stop()
            
        # Update UI
        self.status_label.setText("Status: Stopped")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.log_message("Process stopped")
    
    def check_process_status(self):
        """Check if the launched process is still running"""
        if self.launcher is None:
            return
            
        if not self.launcher.is_running():
            # Process has finished
            return_code = self.launcher.get_return_code()
            self.launcher = None
            self.process_monitor_timer.stop()
            
            # Update UI
            if return_code == 0:
                self.status_label.setText("Status: Completed")
                self.log_message("Process completed successfully")
            else:
                self.status_label.setText("Status: Failed")
                self.log_message(f"Process failed with return code: {return_code}")
            
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.progress_bar.setVisible(False)
    

    
    def log_message(self, message: str):
        """Add message to log display"""
        self.log_display.append(f"[{QTimer().remainingTime()}] {message}")
    
    def clear_logs(self):
        """Clear log display"""
        self.log_display.clear()
    
    def on_close_event(self, event):
        """Handle window close event"""
        if self.launcher and self.launcher.is_running():
            reply = QMessageBox.question(
                self, 
                "Confirm Exit", 
                "A process is still running. Do you want to stop it and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.stop_pipeline()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def main():
    """Main entry point for GUI"""
    if not PYQT_AVAILABLE:
        print("PyQt6 is required for the GUI. Install it with: pip install PyQt6")
        sys.exit(1)
    
    app = QApplication(sys.argv)
    app.setApplicationName("EvilEye")
    app.setApplicationVersion("1.0.0")
    
    # Create and show main window
    window = EvilEyeGUI()
    window.show()
    
    # Run application
    sys.exit(app.exec())


def launch_main_app():
    """Launch the main EvilEye application with GUI"""
    import subprocess
    import sys
    from pathlib import Path
    
    # Get the project root directory
    project_root = Path(__file__).parent.parent
    
    # Launch the main process.py
    process_script = project_root / "process.py"
    
    if not process_script.exists():
        print(f"Error: process.py not found at {process_script}")
        sys.exit(1)
    
    try:
        # Launch with GUI enabled
        subprocess.run([sys.executable, str(process_script), "--gui"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error launching main application: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("Application interrupted by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
