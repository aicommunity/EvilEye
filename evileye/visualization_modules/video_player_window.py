"""
Окно для воспроизведения видеофрагментов событий
"""

import os
import sys
from pathlib import Path
from typing import Optional

try:
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
    from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QTimer
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
    from PyQt5.QtCore import Qt, QUrl, pyqtSignal, QTimer
    try:
        from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
        from PyQt5.QtMultimediaWidgets import QVideoWidget
        pyqt5_multimedia_available = True
    except ImportError:
        pyqt5_multimedia_available = False
    pyqt_version = 5

# Import cv2 for OpenCV fallback (always try to import)
try:
    import cv2
except ImportError:
    cv2 = None

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from ..core.logger import get_module_logger
import logging


class VideoPlayerWidget(QWidget):
    """Виджет для воспроизведения видеофрагментов в ячейке таблицы (не окно)"""
    
    stopped = pyqtSignal()  # Сигнал остановки воспроизведения
    
    def __init__(self, parent=None, logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        super().__init__(parent)
        base_name = "evileye.video_player_widget"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)
        
        # No window setup - this is a widget for embedding in table cell
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        
        self.video_path: Optional[str] = None
        self._is_playing = False
        
        # Initialize OpenCV-related attributes (will be set if OpenCV is used)
        self.cap = None
        self.timer = None
        
        # Cell position for tracking which cell this player belongs to
        self._cell_row = None
        self._cell_col = None
        
        # Try to use QMediaPlayer first
        self._use_opencv = False
        if pyqt_version == 6:
            try:
                self.player = QMediaPlayer()
                self.audio_output = QAudioOutput()
                self.player.setAudioOutput(self.audio_output)
                self.video_widget = QVideoWidget()
                self.player.setVideoOutput(self.video_widget)
                # Set looping
                self.player.setLoops(QMediaPlayer.Loops.Infinite)
                self.player.mediaStatusChanged.connect(self._on_media_status_changed)
                # Connect error signal to detect FFmpeg errors
                self.player.errorOccurred.connect(self._on_player_error)
            except Exception as e:
                self.logger.warning(f"QMediaPlayer not available, falling back to OpenCV: {e}")
                self._use_opencv = True
        elif pyqt_version == 5:
            if pyqt5_multimedia_available:
                try:
                    self.player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
                    self.video_widget = QVideoWidget()
                    self.player.setVideoOutput(self.video_widget)
                    # Set looping - PyQt5 doesn't have setLoops, use stateChanged to restart
                    self.player.stateChanged.connect(self._on_state_changed)
                    self.player.mediaStatusChanged.connect(self._on_media_status_changed_pyqt5)
                    # Connect error signal to detect FFmpeg errors
                    self.player.error.connect(self._on_player_error)
                except Exception as e:
                    self.logger.warning(f"QMediaPlayer not available, falling back to OpenCV: {e}")
                    self._use_opencv = True
            else:
                self._use_opencv = True
        
        if self._use_opencv:
            # Fallback to OpenCV + QTimer
            if cv2 is None:
                self.logger.error("OpenCV not available, cannot use fallback video playback")
                # Create a dummy widget that shows error message
                self.video_widget = QLabel()
                self.video_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.video_widget.setText("OpenCV not available for video playback")
            else:
                self.video_widget = QLabel()
                self.video_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.video_widget.setText("Loading video...")
            # Initialize timer for OpenCV (cap is already None from __init__)
            self.timer = QTimer()
            self.timer.timeout.connect(self._update_frame_opencv)
        
        # Layout - video widget fills the cell
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.video_widget)
        self.setLayout(layout)
        
        # Stop button - positioned on top of video
        self.stop_button = QPushButton("Stop", self)
        self.stop_button.setFixedSize(60, 25)
        # Style button for visibility
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(200, 50, 50, 220);
                color: white;
                border: 1px solid rgba(255, 255, 255, 180);
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(220, 70, 70, 240);
            }
        """)
        self.stop_button.clicked.connect(self.stop)
        # Position button in top-right corner
        self.stop_button.raise_()  # Ensure button is on top
    
    def resizeEvent(self, event):
        """Reposition stop button when widget is resized"""
        super().resizeEvent(event)
        if self.stop_button:
            # Position in top-right corner with small margin
            button_x = self.width() - self.stop_button.width() - 5
            button_y = 5
            self.stop_button.move(button_x, button_y)
            self.stop_button.raise_()
    
    def _on_player_error(self, error, error_string=""):
        """Handle QMediaPlayer errors (FFmpeg errors, etc.)"""
        if pyqt_version == 6:
            from PyQt6.QtMultimedia import QMediaPlayer
            if error_string:
                error_msg = error_string
            else:
                error_msg = str(error)
        else:
            from PyQt5.QtMultimedia import QMediaPlayer
            if error_string:
                error_msg = error_string
            else:
                error_msg = str(error)
        
        # Check for common FFmpeg errors that indicate corrupted/incomplete files
        if "moov atom not found" in error_msg.lower() or "invalid data" in error_msg.lower() or "could not open" in error_msg.lower():
            self.logger.warning(f"Video file appears corrupted or incomplete (FFmpeg error: {error_msg}). Trying OpenCV fallback...")
            # Stop current playback
            if self.player:
                self.player.stop()
            # Switch to OpenCV fallback
            self._use_opencv = True
            # Retry with OpenCV
            if self.video_path:
                self.play_video(self.video_path)
        else:
            self.logger.error(f"QMediaPlayer error: {error_msg}")
    
    def _on_media_status_changed(self, status):
        """Handle media status changes for PyQt6"""
        if pyqt_version == 6:
            from PyQt6.QtMultimedia import QMediaPlayer
            if status == QMediaPlayer.MediaStatus.EndOfMedia:
                # Restart playback for looping
                if self._is_playing and self.player:
                    self.player.setPosition(0)
                    self.player.play()
            elif status == QMediaPlayer.MediaStatus.InvalidMedia:
                # Media is invalid, try OpenCV fallback
                self.logger.warning("QMediaPlayer reports invalid media. Trying OpenCV fallback...")
                if self.video_path:
                    self._use_opencv = True
                    self.play_video(self.video_path)
    
    def _on_state_changed(self, state):
        """Handle state changes for PyQt5"""
        if pyqt_version == 5 and pyqt5_multimedia_available:
            from PyQt5.QtMultimedia import QMediaPlayer
            # This is mainly for debugging, actual looping handled in _on_media_status_changed_pyqt5
            pass
    
    def _on_media_status_changed_pyqt5(self, status):
        """Handle media status changes for PyQt5"""
        if pyqt_version == 5 and pyqt5_multimedia_available:
            from PyQt5.QtMultimedia import QMediaPlayer
            if status == QMediaPlayer.MediaStatus.EndOfMedia:
                # Restart playback for looping
                if self._is_playing and self.player:
                    self.player.setPosition(0)
                    self.player.play()
    
    def _update_frame_opencv(self):
        """Update frame using OpenCV (fallback method) with continuous looping"""
        if not self._is_playing:
            return
        
        if not self.cap or not self.cap.isOpened():
            self.timer.stop()
            return
        
        ret, frame = self.cap.read()
        if not ret:
            # Loop: restart from beginning for continuous playback
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()
            if not ret:
                self.timer.stop()
                return
        
        # Convert BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame_rgb.shape
        bytes_per_line = ch * w
        
        try:
            from PyQt6.QtGui import QImage, QPixmap
        except ImportError:
            from PyQt5.QtGui import QImage, QPixmap
        
        q_image = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)
        
        # Scale to fit widget
        widget_size = self.video_widget.size()
        if widget_size.width() > 0 and widget_size.height() > 0:
            scaled_pixmap = pixmap.scaled(
                widget_size, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            self.video_widget.setPixmap(scaled_pixmap)
    
    def play_video(self, video_path: str):
        """Запустить воспроизведение видеофрагмента"""
        if not video_path or not os.path.exists(video_path):
            self.logger.warning(f"Video file not found: {video_path}")
            return False
        
        # Check file size - if too small, file might be corrupted or incomplete
        try:
            file_size = os.path.getsize(video_path)
            if file_size < 1000:  # Less than 1KB - likely corrupted or empty
                self.logger.warning(f"Video file is too small ({file_size} bytes), likely corrupted: {video_path}")
                return False
        except Exception as e:
            self.logger.warning(f"Error checking video file size: {e}, path={video_path}")
        
        self.video_path = video_path
        self._is_playing = True
        
        if self._use_opencv:
            # Use OpenCV
            if cv2 is None:
                self.logger.error("OpenCV not available for video playback")
                return False
            
            # If we're falling back from QMediaPlayer, replace QVideoWidget with QLabel
            try:
                from PyQt6.QtWidgets import QLabel
                from PyQt6.QtMultimediaWidgets import QVideoWidget
            except ImportError:
                from PyQt5.QtWidgets import QLabel
                from PyQt5.QtMultimediaWidgets import QVideoWidget
            
            if isinstance(self.video_widget, QVideoWidget):
                # Replace QVideoWidget with QLabel for OpenCV
                layout = self.layout()
                if layout:
                    layout.removeWidget(self.video_widget)
                    self.video_widget.deleteLater()
                
                self.video_widget = QLabel()
                self.video_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.video_widget.setText("Loading video...")
                
                if layout:
                    layout.addWidget(self.video_widget)
            
            try:
                self.cap = cv2.VideoCapture(video_path)
                if not self.cap.isOpened():
                    self.logger.error(f"Failed to open video file: {video_path}")
                    return False
                
                # Try to read first frame to check if file is valid
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    self.logger.warning(f"Video file appears to be corrupted or incomplete (cannot read frames): {video_path}")
                    self.cap.release()
                    self.cap = None
                    return False
                # Reset to beginning
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                
                # Start timer for frame updates (30 FPS)
                # Create timer if it doesn't exist (fallback from QMediaPlayer)
                if self.timer is None:
                    self.timer = QTimer()
                    self.timer.timeout.connect(self._update_frame_opencv)
                fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
                interval = int(1000 / fps)
                self.timer.start(interval)
                # Ensure stop button is visible
                if self.stop_button:
                    self.stop_button.raise_()
                return True
            except Exception as e:
                self.logger.error(f"Error opening video with OpenCV: {e}")
                return False
        else:
            # Use QMediaPlayer
            try:
                if pyqt_version == 6:
                    from PyQt6.QtMultimedia import QMediaPlayer
                    self.player.setSource(QUrl.fromLocalFile(video_path))
                    
                    # Check for errors immediately after setting source
                    if self.player.error() != QMediaPlayer.Error.NoError:
                        error_str = self.player.errorString()
                        self.logger.warning(f"QMediaPlayer error after setSource: {error_str}, path={video_path}. Trying OpenCV fallback...")
                        # Fallback to OpenCV if QMediaPlayer fails
                        self._use_opencv = True
                        return self.play_video(video_path)
                    
                    self.player.play()
                    
                    # Check for errors after play
                    if self.player.error() != QMediaPlayer.Error.NoError:
                        error_str = self.player.errorString()
                        self.logger.warning(f"QMediaPlayer error after play: {error_str}, path={video_path}. Trying OpenCV fallback...")
                        self.player.stop()
                        # Fallback to OpenCV if QMediaPlayer fails
                        self._use_opencv = True
                        return self.play_video(video_path)
                else:
                    # PyQt5
                    self.player.setMedia(QMediaContent(QUrl.fromLocalFile(video_path)))
                    self.player.play()
                    
                    # Check for errors (PyQt5 uses error signal)
                    from PyQt5.QtMultimedia import QMediaPlayer
                    if self.player.error() != QMediaPlayer.NoError:
                        error_str = self.player.errorString()
                        self.logger.warning(f"QMediaPlayer error: {error_str}, path={video_path}. Trying OpenCV fallback...")
                        self.player.stop()
                        # Fallback to OpenCV if QMediaPlayer fails
                        self._use_opencv = True
                        return self.play_video(video_path)
                
                # Ensure stop button is visible
                if self.stop_button:
                    self.stop_button.raise_()
                self.logger.info(f"Playing video with QMediaPlayer: {video_path}")
                return True
            except Exception as e:
                self.logger.warning(f"Error playing video with QMediaPlayer: {e}, path={video_path}. Trying OpenCV fallback...")
                # Fallback to OpenCV
                self._use_opencv = True
                return self.play_video(video_path)
    
    def stop(self):
        """Остановить воспроизведение"""
        self._is_playing = False
        
        if self._use_opencv:
            if self.timer:
                self.timer.stop()
            if self.cap:
                self.cap.release()
                self.cap = None
            if self.video_widget:
                # QLabel has clear() method
                try:
                    from PyQt6.QtWidgets import QLabel
                except ImportError:
                    from PyQt5.QtWidgets import QLabel
                if isinstance(self.video_widget, QLabel):
                    self.video_widget.clear()
                    self.video_widget.setText("")
        else:
            if self.player:
                self.player.stop()
            if self.video_widget:
                # QVideoWidget doesn't have clear(), just hide it
                self.video_widget.hide()
        
        # Emit signal - parent will remove widget from cell
        self.stopped.emit()
    
    def set_cell_position(self, row: int, col: int):
        """Set the cell position where this video player is located"""
        self._cell_row = row
        self._cell_col = col


class VideoPlayerWindow(QWidget):
    """Окно для воспроизведения видеофрагментов с зацикливанием"""
    
    stopped = pyqtSignal()  # Сигнал остановки воспроизведения
    
    def __init__(self, parent=None, logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        super().__init__(parent)
        base_name = "evileye.video_player_window"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)
        
        self.setWindowTitle('Video Player')
        self.resize(800, 600)
        
        # Center window on screen or relative to parent
        # Find the top-level window (main window) for proper positioning
        top_level_window = parent
        if parent:
            while top_level_window.parent():
                top_level_window = top_level_window.parent()
        
        if top_level_window:
            # Position relative to top-level window
            try:
                window_rect = top_level_window.geometry()
                self.move(
                    window_rect.x() + (window_rect.width() - 800) // 2,
                    window_rect.y() + (window_rect.height() - 600) // 2
                )
            except Exception:
                # Fallback to screen center if geometry fails
                pass
        
        # If positioning failed or no parent, center on screen
        if self.pos().x() == 0 and self.pos().y() == 0:
            try:
                from PyQt6.QtWidgets import QApplication
            except ImportError:
                from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                screen = app.primaryScreen()
                if screen:
                    screen_geometry = screen.availableGeometry()
                    self.move(
                        screen_geometry.x() + (screen_geometry.width() - 800) // 2,
                        screen_geometry.y() + (screen_geometry.height() - 600) // 2
                    )
        
        self.video_path: Optional[str] = None
        self._is_playing = False
        
        # Try to use QMediaPlayer first
        self._use_opencv = False
        if pyqt_version == 6:
            try:
                self.player = QMediaPlayer()
                self.audio_output = QAudioOutput()
                self.player.setAudioOutput(self.audio_output)
                self.video_widget = QVideoWidget()
                self.player.setVideoOutput(self.video_widget)
                # Set looping
                self.player.setLoops(QMediaPlayer.Loops.Infinite)
                self.player.mediaStatusChanged.connect(self._on_media_status_changed)
                # Connect error signal to detect FFmpeg errors
                self.player.errorOccurred.connect(self._on_player_error)
            except Exception as e:
                self.logger.warning(f"QMediaPlayer not available, falling back to OpenCV: {e}")
                self._use_opencv = True
        elif pyqt_version == 5:
            if pyqt5_multimedia_available:
                try:
                    self.player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
                    self.video_widget = QVideoWidget()
                    self.player.setVideoOutput(self.video_widget)
                    # Set looping - PyQt5 doesn't have setLoops, use stateChanged to restart
                    self.player.stateChanged.connect(self._on_state_changed)
                    self.player.mediaStatusChanged.connect(self._on_media_status_changed_pyqt5)
                    # Connect error signal to detect FFmpeg errors
                    self.player.error.connect(self._on_player_error)
                except Exception as e:
                    self.logger.warning(f"QMediaPlayer not available, falling back to OpenCV: {e}")
                    self._use_opencv = True
            else:
                self._use_opencv = True
        
        if self._use_opencv:
            # Fallback to OpenCV + QTimer
            if cv2 is None:
                self.logger.error("OpenCV not available, cannot use fallback video playback")
                # Create a dummy widget that shows error message
                self.video_widget = QLabel()
                self.video_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.video_widget.setText("OpenCV not available for video playback")
            else:
                self.video_widget = QLabel()
                self.video_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.video_widget.setText("Loading video...")
            self.cap = None
            self.timer = QTimer()
            self.timer.timeout.connect(self._update_frame_opencv)
        
        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.video_widget)
        
        # Stop button
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop)
        layout.addWidget(self.stop_button)
        
        self.setLayout(layout)
    
    def _on_player_error(self, error, error_string=""):
        """Handle QMediaPlayer errors (FFmpeg errors, etc.)"""
        if pyqt_version == 6:
            from PyQt6.QtMultimedia import QMediaPlayer
            if error_string:
                error_msg = error_string
            else:
                error_msg = str(error)
        else:
            from PyQt5.QtMultimedia import QMediaPlayer
            if error_string:
                error_msg = error_string
            else:
                error_msg = str(error)
        
        # Check for common FFmpeg errors that indicate corrupted/incomplete files
        if "moov atom not found" in error_msg.lower() or "invalid data" in error_msg.lower() or "could not open" in error_msg.lower():
            self.logger.warning(f"Video file appears corrupted or incomplete (FFmpeg error: {error_msg}). Trying OpenCV fallback...")
            # Stop current playback
            if self.player:
                self.player.stop()
            # Switch to OpenCV fallback
            self._use_opencv = True
            # Retry with OpenCV
            if self.video_path:
                self.play_video(self.video_path)
        else:
            self.logger.error(f"QMediaPlayer error: {error_msg}")
    
    def _on_media_status_changed(self, status):
        """Handle media status changes for PyQt6"""
        if pyqt_version == 6:
            from PyQt6.QtMultimedia import QMediaPlayer
            if status == QMediaPlayer.MediaStatus.EndOfMedia:
                # Restart playback for looping
                if self._is_playing and self.player:
                    self.player.setPosition(0)
                    self.player.play()
            elif status == QMediaPlayer.MediaStatus.InvalidMedia:
                # Media is invalid, try OpenCV fallback
                self.logger.warning("QMediaPlayer reports invalid media. Trying OpenCV fallback...")
                if self.video_path:
                    self._use_opencv = True
                    self.play_video(self.video_path)
    
    def _on_state_changed(self, state):
        """Handle state changes for PyQt5"""
        if pyqt_version == 5 and pyqt5_multimedia_available:
            from PyQt5.QtMultimedia import QMediaPlayer
            # This is mainly for debugging, actual looping handled in _on_media_status_changed_pyqt5
            pass
    
    def _on_media_status_changed_pyqt5(self, status):
        """Handle media status changes for PyQt5"""
        if pyqt_version == 5 and pyqt5_multimedia_available:
            from PyQt5.QtMultimedia import QMediaPlayer
            if status == QMediaPlayer.MediaStatus.EndOfMedia:
                # Restart playback for looping
                if self._is_playing and self.player:
                    self.player.setPosition(0)
                    self.player.play()
    
    def _update_frame_opencv(self):
        """Update frame using OpenCV (fallback method)"""
        if not self.cap or not self.cap.isOpened():
            self.timer.stop()
            return
        
        ret, frame = self.cap.read()
        if not ret:
            # Loop: restart from beginning
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()
            if not ret:
                self.timer.stop()
                return
        
        # Convert BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame_rgb.shape
        bytes_per_line = ch * w
        
        try:
            from PyQt6.QtGui import QImage, QPixmap
        except ImportError:
            from PyQt5.QtGui import QImage, QPixmap
        
        q_image = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)
        
        # Scale to fit widget
        widget_size = self.video_widget.size()
        if widget_size.width() > 0 and widget_size.height() > 0:
            scaled_pixmap = pixmap.scaled(
                widget_size, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            self.video_widget.setPixmap(scaled_pixmap)
    
    def play_video(self, video_path: str):
        """Запустить воспроизведение видеофрагмента"""
        if not video_path or not os.path.exists(video_path):
            self.logger.warning(f"Video file not found: {video_path}")
            return False
        
        # Check file size - if too small, file might be corrupted or incomplete
        try:
            file_size = os.path.getsize(video_path)
            if file_size < 1000:  # Less than 1KB - likely corrupted or empty
                self.logger.warning(f"Video file is too small ({file_size} bytes), likely corrupted: {video_path}")
                return False
        except Exception as e:
            self.logger.warning(f"Error checking video file size: {e}, path={video_path}")
        
        self.video_path = video_path
        self._is_playing = True
        
        if self._use_opencv:
            # Use OpenCV
            if cv2 is None:
                self.logger.error("OpenCV not available for video playback")
                return False
            try:
                self.cap = cv2.VideoCapture(video_path)
                if not self.cap.isOpened():
                    self.logger.error(f"Failed to open video file: {video_path}")
                    return False
                
                # Try to read first frame to check if file is valid
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    self.logger.warning(f"Video file appears to be corrupted or incomplete (cannot read frames): {video_path}")
                    self.cap.release()
                    self.cap = None
                    return False
                # Reset to beginning
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                
                # Start timer for frame updates (30 FPS)
                fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
                interval = int(1000 / fps)
                self.timer.start(interval)
                return True
            except Exception as e:
                self.logger.error(f"Error opening video with OpenCV: {e}")
                return False
        else:
            # Use QMediaPlayer
            try:
                if pyqt_version == 6:
                    from PyQt6.QtMultimedia import QMediaPlayer
                    self.player.setSource(QUrl.fromLocalFile(video_path))
                    
                    # Check for errors immediately after setting source
                    if self.player.error() != QMediaPlayer.Error.NoError:
                        error_str = self.player.errorString()
                        self.logger.warning(f"QMediaPlayer error after setSource: {error_str}, path={video_path}. Trying OpenCV fallback...")
                        # Fallback to OpenCV if QMediaPlayer fails
                        self._use_opencv = True
                        return self.play_video(video_path)
                    
                    self.player.play()
                    
                    # Check for errors after play
                    if self.player.error() != QMediaPlayer.Error.NoError:
                        error_str = self.player.errorString()
                        self.logger.warning(f"QMediaPlayer error after play: {error_str}, path={video_path}. Trying OpenCV fallback...")
                        self.player.stop()
                        # Fallback to OpenCV if QMediaPlayer fails
                        self._use_opencv = True
                        return self.play_video(video_path)
                else:
                    # PyQt5
                    self.player.setMedia(QMediaContent(QUrl.fromLocalFile(video_path)))
                    self.player.play()
                    
                    # Check for errors (PyQt5 uses error signal)
                    from PyQt5.QtMultimedia import QMediaPlayer
                    if self.player.error() != QMediaPlayer.NoError:
                        error_str = self.player.errorString()
                        self.logger.warning(f"QMediaPlayer error: {error_str}, path={video_path}. Trying OpenCV fallback...")
                        self.player.stop()
                        # Fallback to OpenCV if QMediaPlayer fails
                        self._use_opencv = True
                        return self.play_video(video_path)
                
                self.logger.info(f"Playing video with QMediaPlayer: {video_path}")
                return True
            except Exception as e:
                self.logger.warning(f"Error playing video with QMediaPlayer: {e}, path={video_path}. Trying OpenCV fallback...")
                # Fallback to OpenCV
                self._use_opencv = True
                return self.play_video(video_path)
    
    def stop(self):
        """Остановить воспроизведение"""
        self._is_playing = False
        
        if self._use_opencv:
            if self.timer:
                self.timer.stop()
            if self.cap:
                self.cap.release()
                self.cap = None
            self.video_widget.clear()
            self.video_widget.setText("Stopped")
        else:
            if self.player:
                self.player.stop()
        
        self.stopped.emit()
        self.close()
    
    def closeEvent(self, event):
        """Handle window close"""
        self.stop()
        super().closeEvent(event)
