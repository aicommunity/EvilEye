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

from .pipelines import PipelineSurveillance
from .core import Pipeline


class PipelineWorker(QThread):
    """Worker thread for running the pipeline"""
    
    # Signals
    started = pyqtSignal()
    stopped = pyqtSignal()
    error = pyqtSignal(str)
    log_message = pyqtSignal(str)
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.config = config
        self.pipeline: Optional[Pipeline] = None
        self.running = False
        
    def run(self):
        """Run the pipeline in a separate thread"""
        try:
            self.log_message.emit("Initializing pipeline...")
            
            # Create and initialize pipeline
            self.pipeline = PipelineSurveillance()
            self.pipeline.params = self.config
            
            if not self.pipeline.init():
                self.error.emit("Failed to initialize pipeline")
                return
            
            self.log_message.emit("Pipeline initialized successfully")
            self.started.emit()
            
            # Start pipeline
            self.pipeline.start()
            self.running = True
            self.log_message.emit("Pipeline started")
            
            # Main processing loop
            while self.running:
                try:
                    results = self.pipeline.process()
                    
                    # Check if all sources are finished
                    if self.pipeline.check_all_sources_finished():
                        self.log_message.emit("All sources finished")
                        break
                        
                except Exception as e:
                    self.error.emit(f"Processing error: {e}")
                    break
                    
        except Exception as e:
            self.error.emit(f"Pipeline error: {e}")
        finally:
            if self.pipeline:
                self.pipeline.stop()
                self.pipeline.release()
            self.running = False
            self.stopped.emit()
            self.log_message.emit("Pipeline stopped")
    
    def stop(self):
        """Stop the pipeline"""
        self.running = False


class EvilEyeGUI(QMainWindow):
    """Main GUI window for EvilEye"""
    
    def __init__(self):
        super().__init__()
        self.worker: Optional[PipelineWorker] = None
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("EvilEye - Intelligence Video Surveillance System")
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
        
    def create_main_tab(self) -> QWidget:
        """Create the main tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Title
        title = QLabel("EvilEye Surveillance System")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
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
        control_group = QGroupBox("Controls")
        control_layout = QHBoxLayout(control_group)
        
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self.start_pipeline)
        self.start_btn.setEnabled(False)
        control_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("Stop")
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
            with open(file_path, 'r') as f:
                config = json.load(f)
            
            # Update config editor
            self.config_editor.setPlainText(json.dumps(config, indent=2))
            
            # Store current config
            self.current_config = config
            
            self.log_message(f"Loaded configuration from {file_path}")
            
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
        """Start the pipeline"""
        try:
            # Get configuration from editor
            config_text = self.config_editor.toPlainText()
            config = json.loads(config_text)
            
            # Create and start worker
            self.worker = PipelineWorker(config)
            self.worker.started.connect(self.on_pipeline_started)
            self.worker.stopped.connect(self.on_pipeline_stopped)
            self.worker.error.connect(self.on_pipeline_error)
            self.worker.log_message.connect(self.log_message)
            
            self.worker.start()
            
            # Update UI
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)  # Indeterminate progress
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start pipeline: {e}")
    
    def stop_pipeline(self):
        """Stop the pipeline"""
        if self.worker:
            self.worker.stop()
            self.worker.wait()
    
    def on_pipeline_started(self):
        """Handle pipeline started event"""
        self.status_label.setText("Status: Running")
        self.log_message("Pipeline started")
    
    def on_pipeline_stopped(self):
        """Handle pipeline stopped event"""
        self.status_label.setText("Status: Stopped")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.log_message("Pipeline stopped")
    
    def on_pipeline_error(self, error: str):
        """Handle pipeline error event"""
        self.status_label.setText("Status: Error")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.log_message(f"Pipeline error: {error}")
        QMessageBox.critical(self, "Pipeline Error", error)
    
    def log_message(self, message: str):
        """Add message to log display"""
        self.log_display.append(f"[{QTimer().remainingTime()}] {message}")
    
    def clear_logs(self):
        """Clear log display"""
        self.log_display.clear()


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
