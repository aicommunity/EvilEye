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
from .metadata_overlay_widget import MetadataOverlayWidget
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
        self._current_frame = None  # Текущий кадр для разделения потоков
        self._last_pixmap = None  # Последний отображенный pixmap для перемасштабирования
        self._source_name = None  # Имя источника для метаданных
        self._base_dir = None  # Базовая директория для загрузки метаданных
        self._date_folder = None  # Папка даты для метаданных
        self._metadata_overlay = None  # Виджет метаданных
        self._show_metadata = False  # Показывать ли метаданные
        
        # Initialize OpenCV-related attributes (will be set if OpenCV is used)
        self.cap = None
        self.timer = None
        self._timer_interval = None  # Store timer interval for reuse
        
        # Cell position for tracking which cell this player belongs to
        self._cell_row = None
        self._cell_col = None
        
        # Try to use QMediaPlayer first
        self._use_opencv = False
        self._supported_mime_types = set()  # Кэш поддерживаемых MIME-типов
        
        # Initialize player attributes (will be set based on backend)
        self.player = None  # QMediaPlayer instance (if using QMediaPlayer)
        self.audio_output = None  # QAudioOutput instance (PyQt6 only)
        self.video_widget = None  # QVideoWidget or QLabel instance
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
                # Получить список поддерживаемых MIME-типов
                try:
                    from PyQt6.QtMultimedia import QMediaPlayer
                    self._supported_mime_types = set(QMediaPlayer.supportedMimeTypes())
                    self.logger.debug(f"QMediaPlayer supports {len(self._supported_mime_types)} MIME types")
                except Exception as e:
                    self.logger.debug(f"Could not get supported MIME types: {e}")
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
                    # Получить список поддерживаемых форматов (PyQt5 использует supportedFormats)
                    try:
                        from PyQt5.QtMultimedia import QMediaPlayer
                        # PyQt5 может не иметь supportedMimeTypes, используем supportedFormats
                        if hasattr(QMediaPlayer, 'supportedMimeTypes'):
                            self._supported_mime_types = set(QMediaPlayer.supportedMimeTypes())
                        else:
                            # Fallback: используем известные MIME-типы для видео
                            self._supported_mime_types = {
                                'video/mp4', 'video/x-msvideo', 'video/quicktime',
                                'video/x-matroska', 'video/webm', 'video/ogg'
                            }
                        self.logger.debug(f"QMediaPlayer supports {len(self._supported_mime_types)} MIME types")
                    except Exception as e:
                        self.logger.debug(f"Could not get supported MIME types: {e}")
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
            self._timer_interval = None  # Store timer interval for reuse
        
        # Layout - video widget fills the cell
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.video_widget)
        
        # Создать overlay для метаданных (поверх видео)
        # Используем абсолютное позиционирование для наложения поверх видео
        self._metadata_overlay = MetadataOverlayWidget(self)
        self._metadata_overlay.hide()  # По умолчанию скрыт
        self._metadata_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._metadata_overlay.lower()  # Поместить под другие виджеты, но поверх видео
        
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
        """Reposition stop button when widget is resized and rescale video frame"""
        super().resizeEvent(event)
        if self.stop_button:
            # Position in top-right corner with small margin
            button_x = self.width() - self.stop_button.width() - 5
            button_y = 5
            self.stop_button.move(button_x, button_y)
            self.stop_button.raise_()
        
        # Перемасштабировать последний кадр если используется OpenCV и виджет видим
        if self._use_opencv and self.isVisible() and self._last_pixmap is not None:
            widget_size = self.video_widget.size()
            if widget_size.width() > 0 and widget_size.height() > 0:
                scaled_pixmap = self._last_pixmap.scaled(
                    widget_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.video_widget.setPixmap(scaled_pixmap)
        
        # Обновить размер и позицию overlay метаданных
        if self._metadata_overlay:
            self._metadata_overlay.setGeometry(0, 0, self.width(), self.height())
            self._metadata_overlay.lower()  # Под кнопкой, но поверх видео
    
    def _get_mime_type_from_file(self, file_path: str) -> str:
        """Определить MIME-тип файла по расширению"""
        ext = os.path.splitext(file_path)[1].lower()
        mime_map = {
            '.mp4': 'video/mp4',
            '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime',
            '.mkv': 'video/x-matroska',
            '.webm': 'video/webm',
            '.ogv': 'video/ogg',
            '.m4v': 'video/mp4',
            '.flv': 'video/x-flv',
            '.wmv': 'video/x-ms-wmv',
            '.3gp': 'video/3gpp',
            '.3g2': 'video/3gpp2',
        }
        return mime_map.get(ext, 'video/mp4')  # По умолчанию mp4
    
    def _is_mime_type_supported(self, mime_type: str) -> bool:
        """Проверить, поддерживается ли MIME-тип QMediaPlayer"""
        if not self._supported_mime_types:
            # Если список пуст, предполагаем поддержку (fallback на проверку во время воспроизведения)
            return True
        # Проверить точное совпадение или частичное (например, video/*)
        if mime_type in self._supported_mime_types:
            return True
        # Проверить общий тип (например, video/*)
        base_type = mime_type.split('/')[0] + '/*'
        if base_type in self._supported_mime_types:
            return True
        return False
    
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
        
        # Check for common FFmpeg errors that require fallback to OpenCV
        error_lower = error_msg.lower()
        should_fallback = (
            "moov atom not found" in error_lower or
            "invalid data" in error_lower or
            "could not open" in error_lower or
            "failed setup for format cuda" in error_lower or
            "hwaccel initialisation returned error" in error_lower or
            ("video width" in error_lower and "not within range" in error_lower)
        )
        
        if should_fallback:
            self.logger.warning(f"QMediaPlayer/FFmpeg error detected (FFmpeg error: {error_msg}). Trying OpenCV fallback...")
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
            elif status == QMediaPlayer.MediaStatus.LoadingMedia:
                # Check for errors during loading (e.g., CUDA errors)
                if self.player and self.player.error() != QMediaPlayer.Error.NoError:
                    error_str = self.player.errorString()
                    error_lower = error_str.lower()
                    if ("failed setup for format cuda" in error_lower or
                        "hwaccel initialisation returned error" in error_lower or
                        ("video width" in error_lower and "not within range" in error_lower)):
                        self.logger.warning(f"CUDA/hardware acceleration error detected during loading: {error_str}. Switching to OpenCV fallback...")
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
        # Логирование для диагностики split players
        timer_was_active = self.timer.isActive() if self.timer else False
        cap_opened = self.cap.isOpened() if self.cap else False
        self.logger.debug(f"_update_frame_opencv: Entry - _is_playing={self._is_playing}, timer_active={timer_was_active}, cap_opened={cap_opened}, source={getattr(self, '_source_name', 'unknown')}")
        
        if not self._is_playing:
            if timer_was_active:
                self.logger.warning(f"_update_frame_opencv: Timer was active but _is_playing=False, stopping timer (source={getattr(self, '_source_name', 'unknown')})")
            return
        
        if not self.cap or not self.cap.isOpened():
            cap_exists = self.cap is not None
            cap_opened = self.cap.isOpened() if self.cap else False
            if timer_was_active:
                self.logger.warning(f"_update_frame_opencv: Timer was active but cap not opened (cap={cap_exists}, isOpened={cap_opened}), stopping timer (source={getattr(self, '_source_name', 'unknown')})")
            if self.timer:
                self.timer.stop()
            return
        
        ret, frame = self.cap.read()
        if not ret:
            # Loop: restart from beginning for continuous playback
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cap.read()
            if not ret:
                self.logger.warning(f"_update_frame_opencv: Failed to read frame even after restart, stopping timer (source={getattr(self, '_source_name', 'unknown')})")
                if self.timer:
                    self.timer.stop()
                return
        
        # Сохранить текущий кадр для разделения потоков (ВАЖНО: всегда сохранять, даже если виджет скрыт)
        self._current_frame = frame.copy() if frame is not None else None
        
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
        
        # Scale to fit widget (только если виджет видим и имеет размер)
        widget_size = self.video_widget.size()
        if widget_size.width() > 0 and widget_size.height() > 0:
            scaled_pixmap = pixmap.scaled(
                widget_size, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            self.video_widget.setPixmap(scaled_pixmap)
            # Сохранить оригинальный pixmap для перемасштабирования при изменении размера
            self._last_pixmap = pixmap
            
            # Обновить размер overlay и метаданные
            if self._metadata_overlay:
                self._metadata_overlay.set_video_size(w, h)
                self._metadata_overlay.setGeometry(0, 0, widget_size.width(), widget_size.height())
                if self._show_metadata:
                    self._update_metadata_overlay()
    
    def play_video(self, video_path: str):
        """Запустить воспроизведение видеофрагмента"""
        # Преобразовать в абсолютный путь если нужно
        if video_path and not os.path.isabs(video_path):
            video_path = os.path.abspath(video_path)
        
        if not video_path or not os.path.exists(video_path):
            self.logger.warning(f"Video file not found: {video_path}")
            return False
        
        # Check file size - if too small, file might be corrupted or incomplete
        try:
            file_size = os.path.getsize(video_path)
            if file_size < 1024:  # Less than 1KB - likely corrupted or empty
                self.logger.warning(f"Video file is too small ({file_size} bytes), likely corrupted: {video_path}")
                return False
        except Exception as e:
            self.logger.warning(f"Error checking video file size: {e}, path={video_path}")
            return False
        
        self.video_path = video_path
        self._is_playing = True
        
        # Проверить поддержку MIME-типа перед использованием QMediaPlayer
        if not self._use_opencv and self._supported_mime_types:
            mime_type = self._get_mime_type_from_file(video_path)
            if not self._is_mime_type_supported(mime_type):
                self.logger.info(f"MIME type {mime_type} not supported by QMediaPlayer, using OpenCV fallback: {video_path}")
                self._use_opencv = True
        
        # Проверить валидность файла и размер видео перед использованием QMediaPlayer
        # CUDA декодер mpeg4 не поддерживает ширину > 2048
        # Также проверяем, можно ли открыть файл через OpenCV (быстрая проверка на поврежденные файлы)
        if not self._use_opencv and cv2 is not None:
            try:
                cap_test = cv2.VideoCapture(video_path)
                if cap_test.isOpened():
                    # Проверить, можно ли прочитать первый кадр (проверка на поврежденные файлы)
                    ret, frame = cap_test.read()
                    if not ret or frame is None:
                        # Файл поврежден или неполный - использовать OpenCV напрямую
                        self.logger.warning(f"Video file appears corrupted or incomplete (cannot read frames), using OpenCV fallback: {video_path}")
                        cap_test.release()
                        self._use_opencv = True
                    else:
                        width = int(cap_test.get(cv2.CAP_PROP_FRAME_WIDTH))
                        cap_test.release()
                        # Если ширина > 2048, использовать OpenCV напрямую (CUDA не поддерживает)
                        if width > 2048:
                            self.logger.info(f"Video width {width} exceeds CUDA limit (2048), using OpenCV fallback")
                            self._use_opencv = True
                else:
                    # Не удалось открыть файл через OpenCV - попробовать через QMediaPlayer
                    # (может быть проблема с кодеками, но файл валиден)
                    cap_test.release()
            except Exception as e:
                self.logger.debug(f"Could not check video file validity: {e}")
        
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
                # QTimer is imported at module level - use it directly
                if self.timer is None:
                    # Import QTimer explicitly to avoid scope issues
                    if pyqt_version == 6:
                        from PyQt6.QtCore import QTimer as QtTimer
                    else:
                        from PyQt5.QtCore import QTimer as QtTimer
                    self.timer = QtTimer()
                    self.timer.timeout.connect(self._update_frame_opencv)
                fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
                interval = int(1000 / fps)
                # Сохранить интервал для последующего использования
                self._timer_interval = interval
                timer_was_active = self.timer.isActive() if self.timer else False
                self.timer.start(interval)
                timer_is_active = self.timer.isActive() if self.timer else False
                self.logger.debug(f"play_video: Timer started (was_active={timer_was_active}, is_active={timer_is_active}, interval={interval}ms, fps={fps}, source={getattr(self, '_source_name', 'unknown')})")
                # Ensure stop button is visible
                if self.stop_button:
                    self.stop_button.raise_()
                return True
            except Exception as e:
                self.logger.error(f"Error opening video with OpenCV: {e}")
                # Clean up on error
                if self.cap:
                    try:
                        self.cap.release()
                    except:
                        pass
                    self.cap = None
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
                        error_lower = error_str.lower()
                        # Check for CUDA/hardware acceleration errors
                        if ("failed setup for format cuda" in error_lower or
                            "hwaccel initialisation returned error" in error_lower or
                            ("video width" in error_lower and "not within range" in error_lower)):
                            self.logger.warning(f"CUDA/hardware acceleration error detected: {error_str}. Trying OpenCV fallback...")
                        else:
                            self.logger.warning(f"QMediaPlayer error after setSource: {error_str}, path={video_path}. Trying OpenCV fallback...")
                        # Fallback to OpenCV if QMediaPlayer fails
                        self._use_opencv = True
                        return self.play_video(video_path)
                    
                    self.player.play()
                    
                    # Check for errors after play (with a small delay to allow CUDA errors to surface)
                    def check_errors_after_play():
                        if self.player and self.player.error() != QMediaPlayer.Error.NoError:
                            error_str = self.player.errorString()
                            error_lower = error_str.lower()
                            if ("failed setup for format cuda" in error_lower or
                                "hwaccel initialisation returned error" in error_lower or
                                ("video width" in error_lower and "not within range" in error_lower)):
                                self.logger.warning(f"CUDA/hardware acceleration error detected after play: {error_str}. Switching to OpenCV fallback...")
                                self.player.stop()
                                self._use_opencv = True
                                if self.video_path:
                                    self.play_video(self.video_path)
                    
                    # Check errors after a short delay (200ms) to catch CUDA errors
                    # QTimer already imported at module level
                    QTimer.singleShot(200, check_errors_after_play)
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
    
    def set_metadata_config(self, base_dir: str, date_folder: str, source_name: str):
        """Установить конфигурацию для загрузки метаданных"""
        self._base_dir = base_dir
        self._date_folder = date_folder
        self._source_name = source_name
    
    def set_show_metadata(self, show: bool):
        """Включить/выключить отображение метаданных"""
        self._show_metadata = show
        if self._metadata_overlay:
            if show:
                self._metadata_overlay.show()
                self._metadata_overlay.raise_()  # Поднять поверх видео
                self._update_metadata_overlay()
            else:
                self._metadata_overlay.hide()
    
    def update_metadata_for_time(self, timestamp):
        """Обновить метаданные для указанного времени"""
        if not self._show_metadata or not self._metadata_overlay:
            return
        
        if self._base_dir and self._date_folder and self._source_name:
            self._metadata_overlay.load_metadata_for_time(
                timestamp, self._source_name, self._base_dir, self._date_folder
            )
    
    def _update_metadata_overlay(self):
        """Обновить метаданные overlay (вызывается при обновлении кадра)"""
        if not self._show_metadata or not self._metadata_overlay:
            return
        
        # Получить текущее время из видео (если доступно)
        # Для упрощения используем время из имени файла или текущее системное время
        # В реальной реализации нужно получать время из позиции воспроизведения
        import datetime
        current_time = datetime.datetime.now()  # Заглушка - нужно получать из позиции видео
        
        if self._base_dir and self._date_folder and self._source_name:
            self._metadata_overlay.load_metadata_for_time(
                current_time, self._source_name, self._base_dir, self._date_folder
            )
    
    def resizeEvent(self, event):
        """Обработка изменения размера виджета"""
        super().resizeEvent(event)
        if self._metadata_overlay:
            self._metadata_overlay.setGeometry(0, 0, self.width(), self.height())
            self._metadata_overlay.lower()  # Под кнопкой, но поверх видео
    
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
                # Правильная последовательность очистки: stop() → setSource(None)
                try:
                    self.player.stop()
                    # Освободить ресурсы медиаплеера
                    if pyqt_version == 6:
                        self.player.setSource(QUrl())
                    else:
                        from PyQt5.QtMultimedia import QMediaContent
                        self.player.setMedia(QMediaContent())
                except Exception as e:
                    self.logger.debug(f"Error during player cleanup: {e}")
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
        self._supported_mime_types = set()  # Кэш поддерживаемых MIME-типов
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
                # Получить список поддерживаемых MIME-типов
                try:
                    from PyQt6.QtMultimedia import QMediaPlayer
                    self._supported_mime_types = set(QMediaPlayer.supportedMimeTypes())
                    self.logger.debug(f"QMediaPlayer supports {len(self._supported_mime_types)} MIME types")
                except Exception as e:
                    self.logger.debug(f"Could not get supported MIME types: {e}")
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
                    # Получить список поддерживаемых форматов (PyQt5 использует supportedFormats)
                    try:
                        from PyQt5.QtMultimedia import QMediaPlayer
                        # PyQt5 может не иметь supportedMimeTypes, используем supportedFormats
                        if hasattr(QMediaPlayer, 'supportedMimeTypes'):
                            self._supported_mime_types = set(QMediaPlayer.supportedMimeTypes())
                        else:
                            # Fallback: используем известные MIME-типы для видео
                            self._supported_mime_types = {
                                'video/mp4', 'video/x-msvideo', 'video/quicktime',
                                'video/x-matroska', 'video/webm', 'video/ogg'
                            }
                        self.logger.debug(f"QMediaPlayer supports {len(self._supported_mime_types)} MIME types")
                    except Exception as e:
                        self.logger.debug(f"Could not get supported MIME types: {e}")
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
    
    def _get_mime_type_from_file(self, file_path: str) -> str:
        """Определить MIME-тип файла по расширению"""
        ext = os.path.splitext(file_path)[1].lower()
        mime_map = {
            '.mp4': 'video/mp4',
            '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime',
            '.mkv': 'video/x-matroska',
            '.webm': 'video/webm',
            '.ogv': 'video/ogg',
            '.m4v': 'video/mp4',
            '.flv': 'video/x-flv',
            '.wmv': 'video/x-ms-wmv',
            '.3gp': 'video/3gpp',
            '.3g2': 'video/3gpp2',
        }
        return mime_map.get(ext, 'video/mp4')  # По умолчанию mp4
    
    def _is_mime_type_supported(self, mime_type: str) -> bool:
        """Проверить, поддерживается ли MIME-тип QMediaPlayer"""
        if not self._supported_mime_types:
            # Если список пуст, предполагаем поддержку (fallback на проверку во время воспроизведения)
            return True
        # Проверить точное совпадение или частичное (например, video/*)
        if mime_type in self._supported_mime_types:
            return True
        # Проверить общий тип (например, video/*)
        base_type = mime_type.split('/')[0] + '/*'
        if base_type in self._supported_mime_types:
            return True
        return False
    
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
        
        # Check for common FFmpeg errors that require fallback to OpenCV
        error_lower = error_msg.lower()
        should_fallback = (
            "moov atom not found" in error_lower or
            "invalid data" in error_lower or
            "could not open" in error_lower or
            "failed setup for format cuda" in error_lower or
            "hwaccel initialisation returned error" in error_lower or
            ("video width" in error_lower and "not within range" in error_lower)
        )
        
        if should_fallback:
            self.logger.warning(f"QMediaPlayer/FFmpeg error detected (FFmpeg error: {error_msg}). Trying OpenCV fallback...")
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
            elif status == QMediaPlayer.MediaStatus.LoadingMedia:
                # Check for errors during loading (e.g., CUDA errors)
                if self.player and self.player.error() != QMediaPlayer.Error.NoError:
                    error_str = self.player.errorString()
                    error_lower = error_str.lower()
                    if ("failed setup for format cuda" in error_lower or
                        "hwaccel initialisation returned error" in error_lower or
                        ("video width" in error_lower and "not within range" in error_lower)):
                        self.logger.warning(f"CUDA/hardware acceleration error detected during loading: {error_str}. Switching to OpenCV fallback...")
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
        # Преобразовать в абсолютный путь если нужно
        if video_path and not os.path.isabs(video_path):
            video_path = os.path.abspath(video_path)
        
        if not video_path or not os.path.exists(video_path):
            self.logger.warning(f"Video file not found: {video_path}")
            return False
        
        # Check file size - if too small, file might be corrupted or incomplete
        try:
            file_size = os.path.getsize(video_path)
            if file_size < 1024:  # Less than 1KB - likely corrupted or empty
                self.logger.warning(f"Video file is too small ({file_size} bytes), likely corrupted: {video_path}")
                return False
        except Exception as e:
            self.logger.warning(f"Error checking video file size: {e}, path={video_path}")
            return False
        
        self.video_path = video_path
        self._is_playing = True
        
        # Проверить поддержку MIME-типа перед использованием QMediaPlayer
        if not self._use_opencv and self._supported_mime_types:
            mime_type = self._get_mime_type_from_file(video_path)
            if not self._is_mime_type_supported(mime_type):
                self.logger.info(f"MIME type {mime_type} not supported by QMediaPlayer, using OpenCV fallback: {video_path}")
                self._use_opencv = True
        
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
                        error_lower = error_str.lower()
                        # Check for CUDA/hardware acceleration errors
                        if ("failed setup for format cuda" in error_lower or
                            "hwaccel initialisation returned error" in error_lower or
                            ("video width" in error_lower and "not within range" in error_lower)):
                            self.logger.warning(f"CUDA/hardware acceleration error detected: {error_str}. Trying OpenCV fallback...")
                        else:
                            self.logger.warning(f"QMediaPlayer error after setSource: {error_str}, path={video_path}. Trying OpenCV fallback...")
                        # Fallback to OpenCV if QMediaPlayer fails
                        self._use_opencv = True
                        return self.play_video(video_path)
                    
                    self.player.play()
                    
                    # Check for errors after play (with a small delay to allow CUDA errors to surface)
                    def check_errors_after_play():
                        if self.player and self.player.error() != QMediaPlayer.Error.NoError:
                            error_str = self.player.errorString()
                            error_lower = error_str.lower()
                            if ("failed setup for format cuda" in error_lower or
                                "hwaccel initialisation returned error" in error_lower or
                                ("video width" in error_lower and "not within range" in error_lower)):
                                self.logger.warning(f"CUDA/hardware acceleration error detected after play: {error_str}. Switching to OpenCV fallback...")
                                self.player.stop()
                                self._use_opencv = True
                                if self.video_path:
                                    self.play_video(self.video_path)
                    
                    # Check errors after a short delay (200ms) to catch CUDA errors
                    # QTimer already imported at module level
                    QTimer.singleShot(200, check_errors_after_play)
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
                # Правильная последовательность очистки: stop() → setSource(None)
                try:
                    self.player.stop()
                    # Освободить ресурсы медиаплеера
                    if pyqt_version == 6:
                        self.player.setSource(QUrl())
                    else:
                        from PyQt5.QtMultimedia import QMediaContent
                        self.player.setMedia(QMediaContent())
                except Exception as e:
                    self.logger.debug(f"Error during player cleanup: {e}")
        
        self.stopped.emit()
        self.close()
    
    def closeEvent(self, event):
        """Handle window close"""
        # Убедиться, что все ресурсы освобождены
        self.stop()
        
        # Дополнительная очистка для QMediaPlayer
        if not self._use_opencv and self.player:
            try:
                if pyqt_version == 6:
                    self.player.setSource(QUrl())
                else:
                    from PyQt5.QtMultimedia import QMediaContent
                    self.player.setMedia(QMediaContent())
            except Exception as e:
                self.logger.debug(f"Error during final cleanup: {e}")
        
        super().closeEvent(event)
