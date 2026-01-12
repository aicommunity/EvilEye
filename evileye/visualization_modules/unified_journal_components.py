"""
Унифицированные компоненты для журналов (делегаты, окна изображений)
Работают с любым источником данных (БД или JSON)
"""

import os
import datetime
from typing import Optional, List, Tuple

try:
    from PyQt6.QtCore import Qt, QSize, QPointF, QRect, QUrl
    from PyQt6.QtWidgets import QStyledItemDelegate, QLabel, QVBoxLayout, QTableWidget, QWidget, QTabWidget
    from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QPolygonF
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PyQt6.QtMultimediaWidgets import QVideoWidget
    pyqt_version = 6
    pyqt_multimedia_available = True
except ImportError:
    from PyQt5.QtCore import Qt, QSize, QPointF, QRect, QUrl
    from PyQt5.QtWidgets import QStyledItemDelegate, QLabel, QVBoxLayout, QTableWidget, QWidget, QTabWidget
    from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QPolygonF
    try:
        from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
        from PyQt5.QtMultimediaWidgets import QVideoWidget
        pyqt_multimedia_available = True
    except ImportError:
        pyqt_multimedia_available = False
    pyqt_version = 5

from ..core.logger import get_module_logger
from .journal_metadata_extractor import EventMetadataExtractor
from .journal_path_resolver import JournalPathResolver
import logging


class UnifiedImageDelegate(QStyledItemDelegate):
    """Универсальный делегат для отображения изображений в журналах"""
    
    def __init__(self, parent=None, base_dir=None, db_connection_name=None, 
                 journal_type='objects', journal_widget=None, logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        super().__init__(parent)
        base_name = "evileye.unified_image_delegate"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)
        self.base_dir = base_dir
        self.db_connection_name = db_connection_name
        self.journal_type = journal_type  # 'objects' or 'events'
        self.journal_widget = journal_widget  # Reference to UnifiedEventsJournal for video playback
        self.preview_width = 300
        self.preview_height = 150

    def paint(self, painter, option, index):
        if not index.isValid():
            return
        
        # Get preview data from UserRole (contains both found and lost paths)
        preview_data = index.data(Qt.ItemDataRole.UserRole)
        if not preview_data or not isinstance(preview_data, dict):
            # Fallback to old format for compatibility
            img_path = index.data(Qt.ItemDataRole.DisplayRole)
            if not img_path:
                return
            event_data = index.data(Qt.ItemDataRole.UserRole)
            date_folder = event_data.get('date_folder', '') if event_data else ''
            full_path = self._resolve_image_path(img_path, date_folder)
            if not full_path or not os.path.exists(full_path):
                return
            # Use old logic for backward compatibility
            self._paint_image_old(painter, option, index, full_path, event_data)
            return
        
        # New format: get current mode and corresponding path
        current_mode = preview_data.get('current_mode', 'found')
        if current_mode == 'found':
            img_path = preview_data.get('found_path', '')
            event_data = preview_data.get('found_event')
        else:  # lost
            img_path = preview_data.get('lost_path', '')
            event_data = preview_data.get('lost_event')
        
        if not img_path:
            return
        
        # Get date_folder from event_data
        date_folder = event_data.get('date_folder', '') if event_data else ''
        
        # Resolve full path
        full_path = self._resolve_image_path(img_path, date_folder)
        if not full_path or not os.path.exists(full_path):
            # Log for debugging
            if hasattr(self, 'logger'):
                self.logger.debug(f"Image not found: img_path={img_path}, date_folder={date_folder}, base_dir={self.base_dir}, resolved={full_path}")
            return
            
        # Load image
        pixmap = QPixmap(full_path)
        if pixmap.isNull():
            return

        # Calculate target rect with aspect fit
        cell_rect = option.rect
        img_w = pixmap.width()
        img_h = pixmap.height()
        if img_w <= 0 or img_h <= 0:
            return
            
        cell_w = cell_rect.width()
        cell_h = cell_rect.height()
        scale = min(cell_w / img_w, cell_h / img_h)
        draw_w = int(img_w * scale)
        draw_h = int(img_h * scale)
        draw_x = cell_rect.x() + (cell_w - draw_w) // 2
        draw_y = cell_rect.y() + (cell_h - draw_h) // 2
        
        # Draw image
        painter.drawPixmap(draw_x, draw_y, draw_w, draw_h, pixmap)
        
        # Try to get bounding box and zone coords from event data
        box = None
        zone_coords = None
        if event_data:
            box = event_data.get('bounding_box') or event_data.get('box')
            zone_coords = event_data.get('zone_coords')
        
        # For bbox normalization: if we have a preview image and coordinates in pixels,
        # try to find original frame image to use its dimensions for normalization
        bbox_img_w = img_w
        bbox_img_h = img_h
        if box and ('preview' in full_path.lower() or 'preview' in img_path.lower()):
            # Check if coordinates are likely in pixels (from original frame)
            is_pixels = False
            if isinstance(box, dict):
                x = float(box.get('x', 0) or 0)
                y = float(box.get('y', 0) or 0)
                w = float(box.get('width', 0) or 0)
                h = float(box.get('height', 0) or 0)
                is_pixels = max(x, y, w, h) > 1.0
            elif isinstance(box, (list, tuple)) and len(box) == 4:
                is_pixels = max(float(v) for v in box) > 1.0
            
            if is_pixels:
                # Try to find original frame image
                frame_path = self._resolve_frame_path(full_path)
                if frame_path and os.path.exists(frame_path):
                    try:
                        frame_pixmap = QPixmap(frame_path)
                        if not frame_pixmap.isNull():
                            bbox_img_w = frame_pixmap.width()
                            bbox_img_h = frame_pixmap.height()
                    except Exception:
                        pass  # Fallback to preview dimensions
        
        # If no data in event_data, try to get from database
        if (not box and not zone_coords) and self.db_connection_name:
            # Try to determine event type from table or event_data
            event_type = None
            if event_data:
                # Map event_type from unified format to DB format
                unified_type = event_data.get('event_type', '')
                type_mapping = {
                    'zone_entered': 'ZoneEvent',
                    'zone_left': 'ZoneEvent',
                    'attr_found': 'AttributeEvent',
                    'attr_lost': 'AttributeEvent',
                    'fov_found': 'FOVEvent',
                    'fov_lost': 'FOVEvent',
                    'found': 'ObjectEvent',
                    'lost': 'ObjectEvent',
                }
                event_type = type_mapping.get(unified_type, '')
            
            # If still no event_type, try to get from table (column 1 - Event)
            if not event_type:
                try:
                    table = self.parent()
                    if table:
                        row = index.row()
                        if row < table.rowCount():
                            event_item = table.item(row, 1)  # Column 1 is Event
                            if event_item:
                                event_type = event_item.text()
                except Exception:
                    pass
            
            # Query database based on event type and column
            if event_type:
                db_box, db_zone_coords = self._get_event_data_from_db(img_path, event_type, index.column())
                if db_box:
                    box = db_box
                if db_zone_coords:
                    zone_coords = db_zone_coords
        
        # Draw overlays if available
        if box or zone_coords:
            self._draw_overlays_from_data(painter, box, zone_coords, draw_x, draw_y, draw_w, draw_h, bbox_img_w, bbox_img_h)
        
        # Get video paths for events journal (independent of Found/Lost buttons)
        found_video_path = preview_data.get('found_video_path') if self.journal_type == 'events' else None
        lost_video_path = preview_data.get('lost_video_path') if self.journal_type == 'events' else None
        current_video_path = found_video_path if current_mode == 'found' else lost_video_path
        
        # Draw switching buttons if both found and lost paths are available
        found_path = preview_data.get('found_path', '')
        lost_path = preview_data.get('lost_path', '')
        has_both_previews = bool(found_path and lost_path)
        
        # Get cell coordinates for video player tracking
        cell_row = index.row()
        cell_col = index.column()
        
        # Draw Found/Lost buttons only if both previews exist
        if has_both_previews:
            self._draw_switching_buttons(painter, option, current_mode, draw_x, draw_y, draw_w, draw_h, 
                                        current_video_path if self.journal_type == 'events' else None, 
                                        has_found_lost=True, cell_row=cell_row, cell_col=cell_col)
        # Draw Play/Stop button independently if video is available (even without Found/Lost buttons)
        elif self.journal_type == 'events' and current_video_path:
            self._draw_switching_buttons(painter, option, current_mode, draw_x, draw_y, draw_w, draw_h,
                                        current_video_path, has_found_lost=False, cell_row=cell_row, cell_col=cell_col)
    
    def _compute_switch_button_rects(self, option, draw_x, draw_y, draw_w, draw_h):
        """
        Compute QRect-ы кнопок Found/Lost в координатах viewport.
        Возвращает (found_rect, lost_rect).
        """
        # Button dimensions (compact, consistent)
        button_spacing = 2
        button_width = max(32, min(40, draw_w // 6 if draw_w > 0 else 36))
        button_height = max(14, min(18, draw_h // 10 if draw_h > 0 else 16))
        total_width = button_width * 2 + button_spacing
        if total_width > draw_w:
            scale = (draw_w - 4) / total_width if draw_w > 4 else 1.0
            button_width = max(28, int(button_width * scale))
            button_height = max(12, int(button_height * scale))
            total_width = button_width * 2 + button_spacing

        # Position buttons at the top-left of the image (viewport coords)
        buttons_y = draw_y + 4
        buttons_x = draw_x + 4

        found_rect = QRect(buttons_x, buttons_y, button_width, button_height)
        lost_rect = QRect(buttons_x + button_width + button_spacing,
                          buttons_y, button_width, button_height)

        # Debug log for geometry
        try:
            self.logger.debug(
                "Switch buttons geom: cell_rect=(%d,%d,%d,%d) img_rect=(%d,%d,%d,%d) "
                "found_rect=(%d,%d,%d,%d) lost_rect=(%d,%d,%d,%d)",
                option.rect.x(), option.rect.y(), option.rect.width(), option.rect.height(),
                draw_x, draw_y, draw_w, draw_h,
                found_rect.x(), found_rect.y(), found_rect.width(), found_rect.height(),
                lost_rect.x(), lost_rect.y(), lost_rect.width(), lost_rect.height(),
            )
        except Exception:
            pass

        return found_rect, lost_rect

    def _draw_switching_buttons(self, painter, option, current_mode, draw_x, draw_y, draw_w, draw_h, video_path=None, has_found_lost=True, cell_row=None, cell_col=None):
        """Draw switching buttons (Found/Lost) on top of the image, and Play/Stop button for events journal"""
        try:
            from PyQt6.QtGui import QColor, QFont
        except ImportError:
            from PyQt5.QtGui import QColor, QFont

        found_rect = None
        lost_rect = None
        
        # Draw Found/Lost buttons only if both previews exist
        if has_found_lost:
            found_rect, lost_rect = self._compute_switch_button_rects(
                option, draw_x, draw_y, draw_w, draw_h
            )
            
            # Draw Found button
            if current_mode == 'found':
                painter.fillRect(found_rect, QColor(100, 150, 255, 200))  # Active: blue
            else:
                painter.fillRect(found_rect, QColor(200, 200, 200, 150))  # Inactive: gray
            painter.setPen(QColor(0, 0, 0))
            painter.drawRect(found_rect)
            painter.setPen(QColor(255, 255, 255) if current_mode == 'found' else QColor(0, 0, 0))
            font = QFont()
            font.setPointSize(9)
            painter.setFont(font)
            painter.drawText(found_rect, Qt.AlignmentFlag.AlignCenter, "Found")
            
            if current_mode == 'lost':
                painter.fillRect(lost_rect, QColor(100, 150, 255, 200))  # Active: blue
            else:
                painter.fillRect(lost_rect, QColor(200, 200, 200, 150))  # Inactive: gray
            painter.setPen(QColor(0, 0, 0))
            painter.drawRect(lost_rect)
            painter.setPen(QColor(255, 255, 255) if current_mode == 'lost' else QColor(0, 0, 0))
            painter.drawText(lost_rect, Qt.AlignmentFlag.AlignCenter, "Lost")
        
        # Draw Play/Stop button for events journal if video is available (independent of Found/Lost)
        if self.journal_type == 'events' and video_path:
            play_rect = self._compute_video_button_rect(option, draw_x, draw_y, draw_w, draw_h, found_rect, lost_rect, has_found_lost)
            if play_rect:
                # Check if video is currently playing in THIS cell
                is_playing = False
                if self.journal_widget and self.journal_widget.video_player:
                    try:
                        player = self.journal_widget.video_player
                        if (hasattr(player, '_cell_row') and hasattr(player, '_cell_col') and
                            player._cell_row == cell_row and player._cell_col == cell_col):
                            is_playing = getattr(player, '_is_playing', False)
                    except (AttributeError, RuntimeError):
                        pass  # Widget was deleted
                
                if is_playing:
                    # Draw Stop button (red)
                    painter.fillRect(play_rect, QColor(200, 100, 100, 200))  # Red for stop
                    painter.setPen(QColor(0, 0, 0))
                    painter.drawRect(play_rect)
                    painter.setPen(QColor(255, 255, 255))
                    painter.drawText(play_rect, Qt.AlignmentFlag.AlignCenter, "■")
                else:
                    # Draw Play button (green)
                    painter.fillRect(play_rect, QColor(100, 200, 100, 200))  # Green for play
                    painter.setPen(QColor(0, 0, 0))
                    painter.drawRect(play_rect)
                    painter.setPen(QColor(255, 255, 255))
                    painter.drawText(play_rect, Qt.AlignmentFlag.AlignCenter, "▶")
    
    def _compute_video_button_rect(self, option, draw_x, draw_y, draw_w, draw_h, found_rect, lost_rect, has_found_lost=True):
        """Compute QRect for Play/Stop button, positioned to the right of Found/Lost buttons or standalone"""
        try:
            from PyQt6.QtCore import QRect
        except ImportError:
            from PyQt5.QtCore import QRect
        
        # Button dimensions (same as Found/Lost if they exist, otherwise use defaults)
        if has_found_lost and found_rect:
            button_width = found_rect.width()
            button_height = found_rect.height()
            button_spacing = 2
            
            # Position to the right of Lost button
            buttons_x = lost_rect.x() + lost_rect.width() + button_spacing
            
            # Check if there's enough space
            if buttons_x + button_width > draw_x + draw_w - 4:
                # Not enough space horizontally, try below Found/Lost buttons
                buttons_y = found_rect.y() + found_rect.height() + button_spacing
                if buttons_y + button_height > draw_y + draw_h - 4:
                    # Not enough space, return None
                    return None
                buttons_x = draw_x + 4
            else:
                buttons_y = found_rect.y()
        else:
            # Standalone Play button (no Found/Lost buttons)
            button_spacing = 2
            button_width = max(32, min(40, draw_w // 6 if draw_w > 0 else 36))
            button_height = max(14, min(18, draw_h // 10 if draw_h > 0 else 16))
            buttons_x = draw_x + 4
            buttons_y = draw_y + 4
        
        return QRect(buttons_x, buttons_y, button_width, button_height)
    
    def _paint_image_old(self, painter, option, index, full_path, event_data):
        """Old paint logic for backward compatibility"""
        # Load image
        pixmap = QPixmap(full_path)
        if pixmap.isNull():
            return

        # Calculate target rect with aspect fit
        cell_rect = option.rect
        img_w = pixmap.width()
        img_h = pixmap.height()
        if img_w <= 0 or img_h <= 0:
            return
            
        cell_w = cell_rect.width()
        cell_h = cell_rect.height()
        scale = min(cell_w / img_w, cell_h / img_h)
        draw_w = int(img_w * scale)
        draw_h = int(img_h * scale)
        draw_x = cell_rect.x() + (cell_w - draw_w) // 2
        draw_y = cell_rect.y() + (cell_h - draw_h) // 2
        
        # Draw image
        painter.drawPixmap(draw_x, draw_y, draw_w, draw_h, pixmap)
        
        # Try to get bounding box and zone coords from event data
        box = None
        zone_coords = None
        if event_data:
            box = event_data.get('bounding_box') or event_data.get('box')
            zone_coords = event_data.get('zone_coords')
        
        # For bbox normalization: if we have a preview image and coordinates in pixels,
        # try to find original frame image to use its dimensions for normalization
        bbox_img_w = img_w
        bbox_img_h = img_h
        if box and ('preview' in full_path.lower()):
            # Check if coordinates are likely in pixels (from original frame)
            is_pixels = False
            if isinstance(box, dict):
                x = float(box.get('x', 0) or 0)
                y = float(box.get('y', 0) or 0)
                w = float(box.get('width', 0) or 0)
                h = float(box.get('height', 0) or 0)
                is_pixels = max(x, y, w, h) > 1.0
            elif isinstance(box, (list, tuple)) and len(box) == 4:
                is_pixels = max(float(v) for v in box) > 1.0
            
            if is_pixels:
                # Try to find original frame image
                frame_path = self._resolve_frame_path(full_path)
                if frame_path and os.path.exists(frame_path):
                    try:
                        frame_pixmap = QPixmap(frame_path)
                        if not frame_pixmap.isNull():
                            bbox_img_w = frame_pixmap.width()
                            bbox_img_h = frame_pixmap.height()
                    except Exception:
                        pass  # Fallback to preview dimensions
        
        # Draw overlays if available
        if box or zone_coords:
            self._draw_overlays_from_data(painter, box, zone_coords, draw_x, draw_y, draw_w, draw_h, bbox_img_w, bbox_img_h)
    
    def editorEvent(self, event, model, option, index):
        """Handle mouse clicks on switching buttons"""
        try:
            from PyQt6.QtCore import QEvent
            from PyQt6.QtWidgets import QTableWidget
        except ImportError:
            from PyQt5.QtCore import QEvent
            from PyQt5.QtWidgets import QTableWidget
        
        if not index.isValid():
            return False
        
        # Only handle left button clicks
        if event.type() != QEvent.Type.MouseButtonPress:
            return False
        
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        
        # Get preview data
        preview_data = index.data(Qt.ItemDataRole.UserRole)
        if not preview_data or not isinstance(preview_data, dict):
            return False
        
        found_path = preview_data.get('found_path', '')
        lost_path = preview_data.get('lost_path', '')
        has_both_previews = bool(found_path and lost_path)
        
        # Get current image path and video path (for Play button)
        current_mode = preview_data.get('current_mode', 'found')
        img_path = found_path if current_mode == 'found' else lost_path
        if not img_path:
            img_path = found_path or lost_path  # Fallback to any available path
        
        # Get video paths for events journal
        found_video_path = preview_data.get('found_video_path') if self.journal_type == 'events' else None
        lost_video_path = preview_data.get('lost_video_path') if self.journal_type == 'events' else None
        current_video_path = found_video_path if current_mode == 'found' else lost_video_path
        if not current_video_path:
            current_video_path = found_video_path or lost_video_path  # Fallback to any available video
        
        if not img_path:
            return False
        
        event_data = preview_data.get('found_event') if current_mode == 'found' else preview_data.get('lost_event')
        if not event_data:
            event_data = preview_data.get('found_event') or preview_data.get('lost_event')
        date_folder = event_data.get('date_folder', '') if event_data else ''
        full_path = self._resolve_image_path(img_path, date_folder)
        if not full_path or not os.path.exists(full_path):
            return False
        
        pixmap = QPixmap(full_path)
        if pixmap.isNull():
            return False
        
        cell_rect = option.rect
        img_w = pixmap.width()
        img_h = pixmap.height()
        if img_w <= 0 or img_h <= 0:
            return False
        
        cell_w = cell_rect.width()
        cell_h = cell_rect.height()
        scale = min(cell_w / img_w, cell_h / img_h)
        draw_w = int(img_w * scale)
        draw_h = int(img_h * scale)
        draw_x = cell_rect.x() + (cell_w - draw_w) // 2
        draw_y = cell_rect.y() + (cell_h - draw_h) // 2
        
        # Build button rects (only if both previews exist)
        found_rect = None
        lost_rect = None
        if has_both_previews:
            found_rect, lost_rect = self._compute_switch_button_rects(
                option, draw_x, draw_y, draw_w, draw_h
            )
        
        # Check for Play/Stop button (events journal only, independent of Found/Lost)
        play_rect = None
        if self.journal_type == 'events' and current_video_path:
            play_rect = self._compute_video_button_rect(option, draw_x, draw_y, draw_w, draw_h, found_rect, lost_rect, has_both_previews)
        
        # Check if click is within button areas (event.pos() is in viewport coords)
        click_pos = event.pos()
        
        # Check Play/Stop button first (events journal, independent of Found/Lost)
        if play_rect and play_rect.contains(click_pos):
            # Clicked on Play/Stop button
            if self.journal_widget and current_video_path:
                row = index.row()
                col = index.column()
                
                # Check if video is playing in THIS cell
                is_playing = False
                if self.journal_widget.video_player:
                    try:
                        player = self.journal_widget.video_player
                        if (hasattr(player, '_cell_row') and hasattr(player, '_cell_col') and
                            player._cell_row == row and player._cell_col == col):
                            is_playing = getattr(player, '_is_playing', False)
                    except (AttributeError, RuntimeError):
                        pass  # Widget was deleted
                
                if is_playing:
                    # Stop video playback - safely
                    try:
                        if self.journal_widget.video_player:
                            self.journal_widget.video_player.stop()
                            # Widget will be removed in _on_video_stopped
                    except (AttributeError, RuntimeError):
                        # Widget was already deleted
                        if self.journal_widget:
                            self.journal_widget.video_player = None
                    return True
                else:
                    # Start video playback
                    # Stop any existing video playback
                    if self.journal_widget.video_player:
                        try:
                            self.journal_widget.video_player.stop()
                        except (AttributeError, RuntimeError):
                            pass  # Widget was already deleted
                        self.journal_widget.video_player = None
                    
                    # Import VideoPlayerWidget
                    try:
                        from .video_player_window import VideoPlayerWidget
                    except ImportError:
                        self.logger.error("Failed to import VideoPlayerWidget")
                        return True
                    
                    # Get table and cell coordinates
                    table = self.parent()
                    if not table or not isinstance(table, QTableWidget):
                        return True
                    
                    # Remove any existing widget from this cell
                    existing_widget = table.cellWidget(row, col)
                    if existing_widget:
                        existing_widget.deleteLater()
                    
                    # Create video player widget
                    self.journal_widget.video_player = VideoPlayerWidget(
                        parent=table,
                        logger_name="video_player", 
                        parent_logger=self.logger
                    )
                    # Set cell position for tracking
                    self.journal_widget.video_player.set_cell_position(row, col)
                    self.journal_widget.video_player.stopped.connect(self._on_video_stopped)
                    
                    # Set widget in cell - this will show video over the image
                    table.setCellWidget(row, col, self.journal_widget.video_player)
                    
                    # Start playback
                    if self.journal_widget.video_player.play_video(current_video_path):
                        # Position already set via set_cell_position
                        pass
                    else:
                        # Playback failed, remove widget
                        table.setCellWidget(row, col, None)
                        self.journal_widget.video_player = None
                    
                    return True

        # Handle Found/Lost buttons (only if both previews exist)
        if has_both_previews and found_rect and found_rect.contains(click_pos):
            # Clicked on Found button
            # Stop video playback if active in this cell
            row = index.row()
            col = index.column()
            if self.journal_widget and self.journal_widget.video_player:
                try:
                    player = self.journal_widget.video_player
                    if (hasattr(player, '_cell_row') and hasattr(player, '_cell_col') and
                        player._cell_row == row and player._cell_col == col):
                        player.stop()
                        # Widget will be removed in _on_video_stopped
                except (AttributeError, RuntimeError):
                    pass  # Widget was already deleted
            
            if preview_data.get('current_mode') != 'found':
                preview_data = preview_data.copy()  # Create a copy to avoid modifying original
                preview_data['current_mode'] = 'found'
                # Update QTableWidgetItem directly
                table = self.parent()
                if table and isinstance(table, QTableWidget):
                    row = index.row()
                    col = index.column()
                    item = table.item(row, col)
                    if item:
                        item.setText(found_path)
                        item.setData(Qt.ItemDataRole.UserRole, preview_data)
                        # Trigger repaint
                        table.viewport().update()
                return True
        
        if has_both_previews and lost_rect and lost_rect.contains(click_pos):
            # Clicked on Lost button
            # Stop video playback if active in this cell
            row = index.row()
            col = index.column()
            if self.journal_widget and self.journal_widget.video_player:
                try:
                    player = self.journal_widget.video_player
                    if (hasattr(player, '_cell_row') and hasattr(player, '_cell_col') and
                        player._cell_row == row and player._cell_col == col):
                        player.stop()
                        # Widget will be removed in _on_video_stopped
                except (AttributeError, RuntimeError):
                    pass  # Widget was already deleted
            
            if preview_data.get('current_mode') != 'lost':
                preview_data = preview_data.copy()  # Create a copy to avoid modifying original
                preview_data['current_mode'] = 'lost'
                # Update QTableWidgetItem directly
                table = self.parent()
                if table and isinstance(table, QTableWidget):
                    row = index.row()
                    col = index.column()
                    item = table.item(row, col)
                    if item:
                        item.setText(lost_path)
                        item.setData(Qt.ItemDataRole.UserRole, preview_data)
                        # Trigger repaint
                        table.viewport().update()
                return True
        
        return False
    
    def _on_video_stopped(self):
        """Handle video player stopped signal"""
        try:
            if self.journal_widget and self.journal_widget.video_player:
                table = self.parent()
                if table and isinstance(table, QTableWidget):
                    # Get coordinates from the video player widget itself
                    try:
                        player = self.journal_widget.video_player
                        row = getattr(player, '_cell_row', None)
                        col = getattr(player, '_cell_col', None)
                        if row is not None and col is not None:
                            # Verify widget is still in this cell
                            current_widget = table.cellWidget(row, col)
                            if current_widget == player:
                                widget_to_remove = player
                                # Remove widget from cell first (this will hide it)
                                table.setCellWidget(row, col, None)
                                # Clear reference before deleting
                                self.journal_widget.video_player = None
                                # Delete widget asynchronously
                                if widget_to_remove:
                                    widget_to_remove.deleteLater()
                                # Trigger repaint to show image again
                                table.viewport().update()
                            else:
                                # Widget was moved or replaced, just clear reference
                                self.journal_widget.video_player = None
                        else:
                            # No coordinates, just clear reference
                            self.journal_widget.video_player = None
                    except (AttributeError, RuntimeError):
                        # Widget was already deleted or invalid
                        if self.journal_widget:
                            self.journal_widget.video_player = None
                else:
                    # Clear reference if no table
                    if self.journal_widget:
                        self.journal_widget.video_player = None
        except (AttributeError, RuntimeError) as e:
            # Widget was already deleted or invalid
            if self.journal_widget:
                self.journal_widget.video_player = None

    def _resolve_image_path(self, img_path: str, date_folder: str = '') -> Optional[str]:
        """Resolve image path to full absolute path"""
        if not img_path:
            return None
        
        # Already absolute
        if os.path.isabs(img_path):
            return img_path if os.path.exists(img_path) else None
        
        # Convert frame paths to preview paths for objects (detected_frames -> FoundPreviews, lost_frames -> LostPreviews)
        if 'detected_frames' in img_path or 'lost_frames' in img_path:
            # Extract filename
            filename = os.path.basename(img_path)
            # Convert _frame.jpeg to _preview.jpeg
            if filename.endswith('_frame.jpeg'):
                preview_filename = filename.replace('_frame.jpeg', '_preview.jpeg')
            elif filename.endswith('_frame.jpg'):
                preview_filename = filename.replace('_frame.jpg', '_preview.jpg')
            else:
                # If no _frame suffix, try to add _preview before extension
                name, ext = os.path.splitext(filename)
                preview_filename = f"{name}_preview{ext}"
            
            # Determine type (found/lost) and corresponding folder
            if 'detected_frames' in img_path:
                preview_dir = 'FoundPreviews'
            else:  # lost_frames
                preview_dir = 'LostPreviews'
            
            # Build path to preview
            if date_folder and self.base_dir:
                preview_path = os.path.join(
                    self.base_dir, 'Detections', date_folder, 'Images', preview_dir, preview_filename
                )
                if os.path.exists(preview_path):
                    return preview_path
            
            # Fallback: try without date_folder (extract from filename if possible)
            if self.base_dir:
                # Try to extract date from filename (format: YYYY-MM-DD_HH-MM-SS...)
                import re
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
                if date_match:
                    extracted_date = date_match.group(1)
                    preview_path = os.path.join(
                        self.base_dir, 'Detections', extracted_date, 'Images', preview_dir, preview_filename
                    )
                    if os.path.exists(preview_path):
                        return preview_path
                
                # Try recent dates
                import datetime
                today = datetime.datetime.now().date()
                yesterday = today - datetime.timedelta(days=1)
                for check_date in [today.strftime('%Y-%m-%d'), yesterday.strftime('%Y-%m-%d')]:
                    preview_path = os.path.join(
                        self.base_dir, 'Detections', check_date, 'Images', preview_dir, preview_filename
                    )
                    if os.path.exists(preview_path):
                        return preview_path
        
        # Relative to base_dir (like old ImageDelegate: os.path.join(self.image_dir, path))
        if self.base_dir:
            # Primary: try direct path (path is relative to base_dir, like in old journal)
            # This matches the old behavior: os.path.join(self.image_dir, path)
            full_path = os.path.join(self.base_dir, img_path)
            if os.path.exists(full_path):
                return full_path
            
            # Fallback: if direct path doesn't exist, try with date_folder
            if date_folder:
                # Try structured paths with date_folder
                filename = os.path.basename(img_path)
                candidates = [
                    os.path.join(self.base_dir, 'Events', date_folder, 'Images', 'FoundPreviews', filename),
                    os.path.join(self.base_dir, 'Events', date_folder, 'Images', 'LostPreviews', filename),
                    os.path.join(self.base_dir, 'Detections', date_folder, 'Images', 'FoundPreviews', filename),
                    os.path.join(self.base_dir, 'Detections', date_folder, 'Images', 'LostPreviews', filename),
                    os.path.join(self.base_dir, 'images', date_folder, img_path),
                    os.path.join(self.base_dir, 'images', date_folder, filename),
                ]
                for cand in candidates:
                    if cand and os.path.exists(cand):
                        return cand
            
            # Fallback: if preview not found for detected_frames/lost_frames, try to find frame
            if ('detected_frames' in img_path or 'lost_frames' in img_path) and date_folder:
                # Try to find frame file as fallback
                frame_filename = os.path.basename(img_path)
                if 'detected_frames' in img_path:
                    frame_dir = 'FoundFrames'
                else:  # lost_frames
                    frame_dir = 'LostFrames'
                frame_path = os.path.join(
                    self.base_dir, 'Detections', date_folder, 'Images', frame_dir, frame_filename
                )
                if os.path.exists(frame_path):
                    return frame_path
            
            # Fallback: try with 'images' prefix (legacy)
            if not img_path.startswith('images') and not img_path.startswith('Events') and not img_path.startswith('Detections'):
                alt_path = os.path.join(self.base_dir, 'images', img_path)
                if os.path.exists(alt_path):
                    return alt_path
            
            # Fallback: try recent dates
            import datetime
            today = datetime.datetime.now().date()
            yesterday = today - datetime.timedelta(days=1)
            for check_date in [today.strftime('%Y-%m-%d'), yesterday.strftime('%Y-%m-%d')]:
                filename = os.path.basename(img_path)
                candidates = [
                    os.path.join(self.base_dir, 'Events', check_date, 'Images', 'FoundPreviews', filename),
                    os.path.join(self.base_dir, 'Events', check_date, 'Images', 'LostPreviews', filename),
                    os.path.join(self.base_dir, 'Detections', check_date, 'Images', 'FoundPreviews', filename),
                    os.path.join(self.base_dir, 'Detections', check_date, 'Images', 'LostPreviews', filename),
                ]
                for cand in candidates:
                    if cand and os.path.exists(cand):
                        return cand
        
        return None

    def _resolve_frame_path(self, preview_path: str) -> Optional[str]:
        """Resolve preview path to original frame path for correct bbox normalization"""
        if not preview_path or 'preview' not in preview_path.lower():
            return None
        
        # Try various replacements to find frame image
        candidates = []
        
        # New structure: FoundPreviews -> FoundFrames, LostPreviews -> LostFrames
        if 'FoundPreviews' in preview_path:
            candidates.append(preview_path.replace('FoundPreviews', 'FoundFrames').replace('_preview.', '_frame.'))
        elif 'LostPreviews' in preview_path:
            candidates.append(preview_path.replace('LostPreviews', 'LostFrames').replace('_preview.', '_frame.'))
        
        # Generic replacements
        candidates.append(preview_path.replace('previews', 'frames').replace('_preview.', '_frame.'))
        candidates.append(preview_path.replace('found_previews', 'found_frames').replace('_preview.', '_frame.'))
        candidates.append(preview_path.replace('lost_previews', 'lost_frames').replace('_preview.', '_frame.'))
        candidates.append(preview_path.replace('detected_previews', 'found_frames').replace('_preview.', '_frame.'))
        
        # Try with base_dir if preview_path is relative
        if self.base_dir:
            filename = os.path.basename(preview_path)
            frame_filename = filename.replace('_preview.', '_frame.').replace('preview', 'frame')
            # Extract date folder from preview_path if possible
            parts = preview_path.split(os.sep)
            date_folder = None
            for i, part in enumerate(parts):
                if part in ('Events', 'Detections') and i + 1 < len(parts):
                    date_folder = parts[i + 1]
                    break
            
            if date_folder:
                candidates.extend([
                    os.path.join(self.base_dir, 'Detections', date_folder, 'Images', 'FoundFrames', frame_filename),
                    os.path.join(self.base_dir, 'Detections', date_folder, 'Images', 'LostFrames', frame_filename),
                    os.path.join(self.base_dir, 'Events', date_folder, 'Images', 'FoundFrames', frame_filename),
                    os.path.join(self.base_dir, 'Events', date_folder, 'Images', 'LostFrames', frame_filename),
                ])
        
        # Check candidates
        for cand in candidates:
            if cand and os.path.exists(cand):
                return cand
        
        return None

    def _draw_overlays(self, painter, event_data: dict, draw_x: int, draw_y: int, 
                      draw_w: int, draw_h: int, img_path: str):
        """Draw bounding box and zone overlays from event data"""
        box = event_data.get('bounding_box') or event_data.get('box')
        zone_coords = event_data.get('zone_coords')
        # Try to get image dimensions from img_path for normalization
        img_w = None
        img_h = None
        if img_path and os.path.exists(img_path):
            try:
                pixmap = QPixmap(img_path)
                if not pixmap.isNull():
                    img_w = pixmap.width()
                    img_h = pixmap.height()
            except Exception:
                pass
        self._draw_overlays_from_data(painter, box, zone_coords, draw_x, draw_y, draw_w, draw_h, img_w, img_h)
    
    def _draw_overlays_from_data(self, painter, box, zone_coords, draw_x: int, draw_y: int, 
                                  draw_w: int, draw_h: int, img_w: int = None, img_h: int = None):
        """Draw bounding box and zone overlays from box and zone_coords data"""
        # Normalize bbox to [x1, y1, x2, y2] in float, skip invalid values
        norm_box = None
        try:
            if box:
                if isinstance(box, dict):
                    # Dict format {x, y, width, height} (pixel or normalized)
                    x = float(box.get('x', 0) or 0)
                    y = float(box.get('y', 0) or 0)
                    w = float(box.get('width', 0) or 0)
                    h = float(box.get('height', 0) or 0)
                    # Check if coordinates are in pixels (need normalization)
                    if img_w and img_h and img_w > 0 and img_h > 0:
                        if max(x, y, w, h) > 1.0:
                            # Coordinates are in pixels, normalize to [0,1]
                            x = x / img_w
                            y = y / img_h
                            w = w / img_w
                            h = h / img_h
                    norm_box = [x, y, x + w, y + h]
                elif isinstance(box, (list, tuple)) and len(box) == 4:
                    coords = [float(v) for v in box]
                    # Check if coordinates are in pixels (need normalization)
                    if img_w and img_h and img_w > 0 and img_h > 0:
                        if max(coords) > 1.0:
                            # Coordinates are in pixels, normalize to [0,1]
                            # Try format [x, y, w, h] first (most common in JSON)
                            x, y, w, h = coords
                            # Check if w and h are reasonable (not too large)
                            if w > 0 and h > 0 and w < img_w * 2 and h < img_h * 2:
                                # Likely [x, y, w, h] in pixels
                                norm_box = [x / img_w, y / img_h, (x + w) / img_w, (y + h) / img_h]
                            else:
                                # Likely [x1, y1, x2, y2] in pixels
                                x1, y1, x2, y2 = coords
                                norm_box = [x1 / img_w, y1 / img_h, x2 / img_w, y2 / img_h]
                        else:
                            # Already normalized [x1, y1, x2, y2] in [0,1]
                            norm_box = coords
                    else:
                        # No image dimensions, assume already normalized
                        norm_box = coords
        except Exception:
            norm_box = None

        # Draw bounding box
        if norm_box:
            painter.setPen(QPen(QColor(0, 255, 0), 2))  # Green for bbox
            try:
                x1, y1, x2, y2 = norm_box
                x = draw_x + int(x1 * draw_w)
                y = draw_y + int(y1 * draw_h)
                w = int((x2 - x1) * draw_w)
                h = int((y2 - y1) * draw_h)
                painter.drawRect(x, y, w, h)
            except Exception:
                pass  # Skip drawing if values are invalid
        
        # Draw zone
        if zone_coords:
            painter.setPen(QPen(QColor(255, 0, 0), 2))  # Red for zone
            painter.setBrush(QBrush(QColor(255, 0, 0, 64)))  # Semi-transparent red fill
            polygon = QPolygonF()
            for pt in zone_coords:
                if isinstance(pt, (list, tuple)) and len(pt) == 2:
                    try:
                        px = float(pt[0])
                        py = float(pt[1])
                        # Normalize if coordinates are in pixels
                        if img_w and img_h and img_w > 0 and img_h > 0:
                            if px > 1.0 or py > 1.0:
                                px = px / img_w
                                py = py / img_h
                    except Exception:
                        continue
                    x = draw_x + int(px * draw_w)
                    y = draw_y + int(py * draw_h)
                    polygon.append(QPointF(x, y))
            if polygon.count() > 0:
                painter.drawPolygon(polygon)

    def _get_event_data_from_db(self, img_path: str, event_type: str, col: int) -> tuple:
        """Get bounding box and zone_coords from database for events"""
        if not self.db_connection_name:
            return None, None
        
        try:
            from PyQt6.QtSql import QSqlDatabase, QSqlQuery
        except ImportError:
            from PyQt5.QtSql import QSqlDatabase, QSqlQuery
        
        box = None
        zone_coords = None
        
        try:
            query = QSqlQuery(QSqlDatabase.database(self.db_connection_name))
            
            # Query based on event type and column (5 = Preview, 6 = Lost preview)
            if event_type == 'ZoneEvent':
                if col == 5:
                    query.prepare('SELECT box_entered, zone_coords FROM zone_events WHERE preview_path_entered = :path')
                else:
                    query.prepare('SELECT box_left, zone_coords FROM zone_events WHERE preview_path_left = :path')
            elif event_type == 'AttributeEvent':
                if col == 5:
                    query.prepare('SELECT box_found FROM attribute_events WHERE preview_path_found = :path')
                else:
                    query.prepare('SELECT box_finished FROM attribute_events WHERE preview_path_finished = :path')
            elif event_type == 'ObjectEvent':
                if col == 5:
                    query.prepare('SELECT bounding_box FROM objects WHERE preview_path = :path')
                else:
                    query.prepare('SELECT lost_bounding_box FROM objects WHERE lost_preview_path = :path')
            else:
                # FOV/Camera events have no bbox
                return None, None
            
            query.bindValue(':path', img_path)
            if query.exec() and query.next():
                # Parse bounding box
                value0 = query.value(0)
                if value0 is not None:
                    box = self._parse_bbox(value0)
                
                # Parse zone coords for ZoneEvent
                if event_type == 'ZoneEvent' and query.record().count() > 1:
                    value1 = query.value(1)
                    if value1 is not None:
                        zone_coords = self._parse_zone_coords(value1)
        
        except Exception as e:
            # Log error but don't fail
            pass
        
        return box, zone_coords
    
    def _parse_zone_coords(self, value) -> Optional[List[Tuple[float, float]]]:
        """Parse zone coordinates from database format"""
        if value is None:
            return None
        try:
            if isinstance(value, str):
                s = value.strip().strip('{}')
                points_str = [p.strip('{} ') for p in s.split('},')]
                coords = []
                for ps in points_str:
                    parts = [pp.strip() for pp in ps.split(',') if pp.strip()]
                    if len(parts) == 2:
                        coords.append((float(parts[0]), float(parts[1])))
                return coords if coords else None
            elif isinstance(value, (list, tuple)):
                return [(float(p[0]), float(p[1])) for p in value if isinstance(p, (list, tuple)) and len(p) == 2]
            elif hasattr(value, 'toString'):
                s = str(value.toString()).strip('{}')
                points_str = [p.strip('{} ') for p in s.split('},')]
                coords = []
                for ps in points_str:
                    parts = [pp.strip() for pp in ps.split(',') if pp.strip()]
                    if len(parts) == 2:
                        coords.append((float(parts[0]), float(parts[1])))
                return coords if coords else None
        except Exception:
            pass
        return None

    def _normalize_bbox(self, box, img_path: str) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """Normalize bounding box to [0,1] range"""
        if not box:
            return None, None, None, None
        
        try:
            # Handle different box formats
            if isinstance(box, dict):
                x = box.get('x', 0)
                y = box.get('y', 0)
                w = box.get('width', 0)
                h = box.get('height', 0)
                if max(x, y, w, h) <= 1.0:
                    return x, y, x + w, y + h
                else:
                    # Need to normalize
                    pixmap = QPixmap(img_path)
                    if not pixmap.isNull() and pixmap.width() > 0 and pixmap.height() > 0:
                        return x / pixmap.width(), y / pixmap.height(), (x + w) / pixmap.width(), (y + h) / pixmap.height()
            elif isinstance(box, (list, tuple)) and len(box) == 4:
                a, b, c, d = box
                if max(a, b, c, d) <= 1.0:
                    # Already normalized [x1, y1, x2, y2]
                    return a, b, c, d
                else:
                    # Assume [x, y, w, h] in pixels
                    pixmap = QPixmap(img_path)
                    if not pixmap.isNull() and pixmap.width() > 0 and pixmap.height() > 0:
                        return a / pixmap.width(), b / pixmap.height(), (a + c) / pixmap.width(), (b + d) / pixmap.height()
        except Exception:
            pass
        
        return None, None, None, None

    def _parse_bbox(self, value) -> Optional[List[float]]:
        """Parse bounding box from database format"""
        if value is None:
            return None
        try:
            if isinstance(value, str):
                s = value.replace('{', '').replace('}', '')
                parts = [p.strip() for p in s.split(',')]
                if len(parts) == 4:
                    return [float(p) for p in parts]
            elif isinstance(value, (list, tuple)):
                if len(value) == 4:
                    return [float(v) for v in value]
        except Exception:
            pass
        return None

    def sizeHint(self, option, index) -> QSize:
        if index.isValid() and index.data(Qt.ItemDataRole.DisplayRole):
            return QSize(self.preview_width, self.preview_height)
        return super().sizeHint(option, index)


class UnifiedDateTimeDelegate(QStyledItemDelegate):
    """Универсальный делегат для отображения дат и времени"""
    
    def __init__(self, parent=None):
        super().__init__(parent)

    def displayText(self, value, locale) -> str:
        """Format datetime to show only seconds precision"""
        try:
            # Handle empty / null-like values аккуратно, без прямого bool(value)
            if value is None:
                return ''
            # Qt может передавать специальные типы (QDateTime/QVariant), для них сначала берём строку
            value_str = str(value).strip()
            if value_str == '' or value_str.lower() in ('none', 'null'):
                return ''
            
            if isinstance(value, str):
                # Handle empty string
                if not value.strip():
                    return ''
                # Parse ISO format datetime string
                if 'T' in value:
                    # ISO format: 2025-09-01T17:30:45.123456
                    try:
                        dt = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
                        return dt.strftime('%Y-%m-%d %H:%M:%S')
                    except Exception:
                        return value
                else:
                    return value
            elif isinstance(value, datetime.datetime):
                return value.strftime('%Y-%m-%d %H:%M:%S')
            return value_str
        except Exception as e:
            return value_str if 'value_str' in locals() and value_str else ''


class UnifiedImageWindow(QWidget):
    """Универсальное окно для просмотра видео и изображений с оверлеями"""
    
    def __init__(self, found_image_path: str, found_event: dict = None, 
                 lost_image_path: str = None, lost_event: dict = None,
                 journal_type: str = 'events', base_dir: str = None,
                 data_source = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Media Viewer')
        try:
            self.setWindowFlag(Qt.Window, True)
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        except Exception:
            pass
        self.setFixedSize(1200, 800)
        
        # Store parameters
        self.found_image_path = found_image_path
        self.found_event = found_event or {}
        self.lost_image_path = lost_image_path
        self.lost_event = lost_event or {}
        self.journal_type = journal_type
        self.base_dir = base_dir
        self.data_source = data_source
        
        # Video player components
        self.video_player = None
        self.video_widget = None
        self.video_path = None
        self.video_offset_seconds = 0
        self._use_opencv = False  # Flag for OpenCV fallback
        
        # Logger
        self.logger = get_module_logger("unified_image_window")
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(False)
        
        # Setup tabs
        self._setup_tabs()
        
        # Setup layout
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.tab_widget)
        self.setLayout(self.layout)
    
    def _setup_tabs(self):
        """Setup video and image tabs"""
        # Tab 1: Video (if available)
        video_path, offset_seconds = self._resolve_video()
        if video_path:
            self.video_path = video_path
            self.video_offset_seconds = offset_seconds
            self._create_video_tab()
        
        # Tab 2: Found image (always visible)
        self._create_found_image_tab()
        
        # Tab 3: Lost image (if available)
        if self.lost_image_path:
            self._create_lost_image_tab()
    
    def _resolve_video(self):
        """Resolve video path based on journal type"""
        if self.journal_type == 'events':
            return self._resolve_event_video()
        elif self.journal_type == 'objects':
            return self._resolve_stream_segment_path()
        return None, 0
    
    def _resolve_event_video(self):
        """Resolve video path for events"""
        if not self.found_event or not self.base_dir:
            return None, 0
        
        # Try to use saved video path from event data (preferred)
        video_path = self.found_event.get('video_path') or self.found_event.get('video_path_entered')
        if video_path:
            full_path = os.path.join(self.base_dir, video_path) if not os.path.isabs(video_path) else video_path
            if os.path.exists(full_path):
                try:
                    file_size = os.path.getsize(full_path)
                    if file_size >= 1000:  # At least 1KB
                        return full_path, 0
                except Exception:
                    pass
        
        # Try lost video path
        video_path = self.found_event.get('video_path_lost') or self.found_event.get('video_path_left')
        if video_path:
            full_path = os.path.join(self.base_dir, video_path) if not os.path.isabs(video_path) else video_path
            if os.path.exists(full_path):
                try:
                    file_size = os.path.getsize(full_path)
                    if file_size >= 1000:
                        return full_path, 0
                except Exception:
                    pass
        
        # Fallback: try to construct path from event data
        # This is a simplified version of _resolve_video_path from UnifiedEventsJournal
        event_type = self.found_event.get('event_type', '')
        time_stamp = self.found_event.get('ts') or self.found_event.get('time_stamp')
        source_name = self.found_event.get('source_name', '')
        event_id_numeric = self.found_event.get('event_id_numeric')
        
        if not all([event_type, time_stamp]):
            return None, 0
        
        # Parse timestamp
        if isinstance(time_stamp, str):
            try:
                dt = datetime.datetime.fromisoformat(time_stamp.replace('Z', '+00:00'))
            except Exception:
                return None, 0
        elif isinstance(time_stamp, datetime.datetime):
            dt = time_stamp
        else:
            return None, 0
        
        date_folder = dt.strftime('%Y-%m-%d')
        time_str = dt.strftime('%Y%m%d_%H%M%S')
        
        # Map event type
        event_name_map = {
            'zone_entered': 'ZoneEvent',
            'zone_left': 'ZoneEvent',
            'attr_found': 'AttributeEvent',
            'attr_lost': 'AttributeEvent',
            'fov_found': 'FOVEvent',
            'fov_lost': 'FOVEvent',
        }
        event_name = event_name_map.get(event_type, event_type)
        
        # Try to find video file
        videos_base_dir = os.path.join(self.base_dir, 'Events', date_folder, 'Videos')
        if not os.path.exists(videos_base_dir):
            return None, 0
        
        # Get possible camera folders
        possible_camera_folders = []
        if source_name:
            possible_camera_folders.append(source_name)
        
        # Try to find video file
        import glob
        for camera_folder in possible_camera_folders:
            camera_path = os.path.join(videos_base_dir, camera_folder)
            if not os.path.isdir(camera_path):
                continue
            
            # Try with event_id_numeric
            if event_id_numeric is not None:
                pattern = f'*_{event_name}_{event_id_numeric}_{time_str}.mp4'
                matching = glob.glob(os.path.join(camera_path, pattern))
                if matching:
                    return matching[0], 0
            
            # Try without event_id
            pattern = f'*_{event_name}_{time_str}.mp4'
            matching = glob.glob(os.path.join(camera_path, pattern))
            if matching:
                return matching[0], 0
            
            # Try partial time match
            time_str_partial = dt.strftime('%Y%m%d_%H%M')
            pattern = f'*_{event_name}_*_{time_str_partial}*.mp4'
            matching = glob.glob(os.path.join(camera_path, pattern))
            if matching:
                return matching[0], 0
        
        return None, 0
    
    def _resolve_stream_segment_path(self):
        """Resolve stream segment path for objects"""
        if not self.found_event or not self.base_dir:
            self.logger.debug("_resolve_stream_segment_path: missing found_event or base_dir")
            return None, 0
        
        # Get timestamp from event
        timestamp = self.found_event.get('ts') or self.found_event.get('time_stamp')
        if not timestamp:
            self.logger.debug("_resolve_stream_segment_path: no timestamp in event")
            return None, 0
        
        # Parse timestamp
        if isinstance(timestamp, str):
            try:
                dt = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except Exception as e:
                self.logger.debug(f"_resolve_stream_segment_path: failed to parse timestamp '{timestamp}': {e}")
                return None, 0
        elif isinstance(timestamp, datetime.datetime):
            dt = timestamp
        else:
            self.logger.debug(f"_resolve_stream_segment_path: invalid timestamp type {type(timestamp)}")
            return None, 0
        
        date_folder = dt.strftime('%Y-%m-%d')
        time_str = dt.strftime('%Y%m%d_%H%M%S')
        
        # Get source name
        source_name = self.found_event.get('source_name', '')
        source_id = self.found_event.get('source_id')
        
        self.logger.debug(f"_resolve_stream_segment_path: event_time={dt}, source_name={source_name}, source_id={source_id}, date_folder={date_folder}")
        
        # Build stream directory path
        streams_dir = os.path.join(self.base_dir, 'Streams', date_folder)
        if not os.path.exists(streams_dir):
            self.logger.debug(f"_resolve_stream_segment_path: streams directory does not exist: {streams_dir}")
            return None, 0
        
        # Try to find camera folder - check all possible folders
        camera_folders = []
        
        # Try exact source_name match
        if source_name:
            camera_folder_path = os.path.join(streams_dir, source_name)
            if os.path.exists(camera_folder_path):
                camera_folders.append(source_name)
                self.logger.debug(f"_resolve_stream_segment_path: found camera folder by source_name: {source_name}")
        
        # Try composite names (for split sources) - check all folders in streams_dir
        if self.data_source and hasattr(self.data_source, '_source_name_id_address'):
            source_mappings = self.data_source._source_name_id_address
            if source_id is not None:
                # Find all source names that map to this source_id
                for src_name, (src_id, address) in source_mappings.items():
                    if src_id == source_id:
                        composite_folder = os.path.join(streams_dir, src_name)
                        if os.path.exists(composite_folder) and src_name not in camera_folders:
                            camera_folders.append(src_name)
                            self.logger.debug(f"_resolve_stream_segment_path: found camera folder by source_id mapping: {src_name}")
        
        # Also check all existing folders in streams_dir (for cases where folder name doesn't match source_name)
        try:
            for folder_name in os.listdir(streams_dir):
                folder_path = os.path.join(streams_dir, folder_name)
                if os.path.isdir(folder_path) and folder_name not in camera_folders:
                    # Check if this folder might contain segments for our source
                    # For split sources, folder might be like "Cam2-Cam3" but source_name is "Cam2"
                    if source_name and (source_name in folder_name or folder_name in source_name):
                        camera_folders.append(folder_name)
                        self.logger.debug(f"_resolve_stream_segment_path: found potential camera folder by name match: {folder_name}")
        except Exception as e:
            self.logger.debug(f"_resolve_stream_segment_path: error listing streams_dir: {e}")
        
        if not camera_folders:
            self.logger.warning(f"_resolve_stream_segment_path: no camera folders found for source_name={source_name}, source_id={source_id}, streams_dir={streams_dir}")
            return None, 0
        
        # Search for segment file
        segment_length_sec = 300  # Default segment length (5 minutes)
        import glob
        
        for camera_folder in camera_folders:
            camera_path = os.path.join(streams_dir, camera_folder)
            if not os.path.isdir(camera_path):
                continue
            
            self.logger.debug(f"_resolve_stream_segment_path: searching in camera folder: {camera_folder}")
            
            # List all segment files in this folder (don't filter by source_name in filename)
            # Format: {source_name}_{YYYYMMDD}_{HHMMSS}_{seq}.mp4
            # But folder might contain segments from multiple sources or with different naming
            all_segments = glob.glob(os.path.join(camera_path, '*.mp4'))
            
            if not all_segments:
                self.logger.debug(f"_resolve_stream_segment_path: no .mp4 files found in {camera_path}")
                continue
            
            self.logger.debug(f"_resolve_stream_segment_path: found {len(all_segments)} segment files in {camera_folder}")
            
            # Find segment that contains the event time
            best_segment = None
            best_offset = 0
            min_time_diff = float('inf')
            
            for segment_file in all_segments:
                filename = os.path.basename(segment_file)
                # Extract start time from filename: {source_name}_{YYYYMMDD}_{HHMMSS}_{seq}.mp4
                # Format: parts[0] = source_name, parts[1] = YYYYMMDD, parts[2] = HHMMSS, parts[3] = seq
                parts = filename.replace('.mp4', '').split('_')
                if len(parts) >= 3:
                    try:
                        date_part = parts[1]  # YYYYMMDD
                        time_part = parts[2]  # HHMMSS
                        segment_start_str = f"{date_part}_{time_part}"
                        segment_start = datetime.datetime.strptime(segment_start_str, '%Y%m%d_%H%M%S')
                        
                        # Check if event time is within this segment
                        segment_end = segment_start + datetime.timedelta(seconds=segment_length_sec)
                        if segment_start <= dt < segment_end:
                            # Calculate offset
                            offset_seconds = (dt - segment_start).total_seconds()
                            self.logger.info(f"_resolve_stream_segment_path: found exact segment match: {filename}, offset={offset_seconds}s")
                            return segment_file, int(offset_seconds)
                        
                        # Track closest segment for fallback
                        time_diff = abs((dt - segment_start).total_seconds())
                        if time_diff < segment_length_sec and time_diff < min_time_diff:
                            min_time_diff = time_diff
                            best_segment = segment_file
                            best_offset = max(0, int((dt - segment_start).total_seconds()))
                    except Exception as e:
                        self.logger.debug(f"_resolve_stream_segment_path: error parsing segment filename '{filename}': {e}")
                        continue
            
            # If exact match not found, use closest segment
            if best_segment:
                self.logger.info(f"_resolve_stream_segment_path: using closest segment: {os.path.basename(best_segment)}, time_diff={min_time_diff}s, offset={best_offset}s")
                return best_segment, best_offset
        
        self.logger.warning(f"_resolve_stream_segment_path: no suitable segment found for event_time={dt}, source_name={source_name}")
        return None, 0
    
    def _create_video_tab(self):
        """Create video tab with player"""
        if not self.video_path:
            return
        
        # Check video file integrity before playing
        if not self._check_video_integrity(self.video_path):
            self.logger.warning(f"Video file integrity check failed: {self.video_path}")
            # Try OpenCV fallback immediately
            self._use_opencv = True
        
        video_container = QWidget()
        video_layout = QVBoxLayout()
        video_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create video player
        if pyqt_multimedia_available and not self._use_opencv:
            try:
                if pyqt_version == 6:
                    self.video_player = QMediaPlayer()
                    self.audio_output = QAudioOutput()
                    self.video_player.setAudioOutput(self.audio_output)
                    self.video_widget = QVideoWidget()
                    self.video_player.setVideoOutput(self.video_widget)
                    self.video_player.setLoops(QMediaPlayer.Loops.Infinite)
                    # Connect error handler
                    self.video_player.errorOccurred.connect(self._on_player_error)
                else:
                    self.video_player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
                    self.video_widget = QVideoWidget()
                    self.video_player.setVideoOutput(self.video_widget)
                    # PyQt5 looping handled in stateChanged
                    self.video_player.stateChanged.connect(self._on_video_state_changed)
                    # Connect error handler
                    self.video_player.error.connect(self._on_player_error)
                
                video_layout.addWidget(self.video_widget)
                video_container.setLayout(video_layout)
                
                # Set video source and play
                video_url = QUrl.fromLocalFile(self.video_path)
                if pyqt_version == 6:
                    self.video_player.setSource(video_url)
                else:
                    self.video_player.setMedia(QMediaContent(video_url))
                
                # Set position if offset specified
                if self.video_offset_seconds > 0:
                    self.video_player.setPosition(self.video_offset_seconds * 1000)
                
                # Start playback
                self.video_player.play()
                
            except Exception as e:
                self.logger.warning(f"Failed to create QMediaPlayer: {e}")
                # Fallback to OpenCV
                self._use_opencv = True
                self._create_opencv_video_player(video_container, video_layout)
        else:
            # Use OpenCV fallback
            self._create_opencv_video_player(video_container, video_layout)
        
        self.tab_widget.addTab(video_container, "Video")
        # Set video tab as active if video is available
        self.tab_widget.setCurrentIndex(0)
    
    def _check_video_integrity(self, video_path: str) -> bool:
        """Check video file integrity before playback
        
        Args:
            video_path: Path to video file
            
        Returns:
            True if file appears valid, False otherwise
        """
        if not video_path or not os.path.exists(video_path):
            return False
        
        try:
            # Check file size (should be > 1KB)
            file_size = os.path.getsize(video_path)
            if file_size < 1000:
                self.logger.warning(f"Video file too small ({file_size} bytes): {video_path}")
                return False
            
            # For MP4 files, check if moov atom exists (basic check)
            if video_path.lower().endswith('.mp4'):
                with open(video_path, 'rb') as f:
                    # Read first 8KB to check for moov atom
                    data = f.read(8192)
                    if b'moov' not in data and b'ftyp' not in data:
                        # Try reading more (moov might be at the end for some encoders)
                        f.seek(-8192, 2)  # Seek to 8KB before end
                        end_data = f.read(8192)
                        if b'moov' not in end_data:
                            self.logger.warning(f"MP4 file missing moov atom: {video_path}")
                            return False
            
            return True
        except Exception as e:
            self.logger.warning(f"Error checking video integrity: {e}")
            return False
    
    def _on_player_error(self, error=None, error_string=""):
        """Handle QMediaPlayer errors (FFmpeg errors, etc.)"""
        if pyqt_version == 6:
            from PyQt6.QtMultimedia import QMediaPlayer
            if error_string:
                error_msg = error_string
            else:
                error_msg = str(error) if error else "Unknown error"
        else:
            from PyQt5.QtMultimedia import QMediaPlayer
            if error_string:
                error_msg = error_string
            else:
                error_msg = str(error) if error else "Unknown error"
        
        # Check for common FFmpeg errors that indicate corrupted/incomplete files
        if "moov atom not found" in error_msg.lower() or "invalid data" in error_msg.lower() or "could not open" in error_msg.lower():
            self.logger.warning(f"Video file appears corrupted or incomplete (FFmpeg error: {error_msg}). Trying OpenCV fallback...")
            # Stop current playback
            if self.video_player:
                try:
                    self.video_player.stop()
                except Exception:
                    pass
            
            # Switch to OpenCV fallback
            self._use_opencv = True
            
            # Remove current video widget and create OpenCV player
            if self.video_widget:
                self.video_widget.setParent(None)
                self.video_widget = None
            
            # Find video container and recreate player
            for i in range(self.tab_widget.count()):
                widget = self.tab_widget.widget(i)
                if widget and widget.findChild(QWidget, "video_container"):
                    video_layout = widget.layout()
                    if video_layout:
                        self._create_opencv_video_player(widget, video_layout)
                        break
        else:
            self.logger.error(f"QMediaPlayer error: {error_msg}")
    
    def _create_opencv_video_player(self, container, layout):
        """Create OpenCV-based video player as fallback"""
        try:
            # Try to import VideoPlayerWidget from video_player_window
            from .video_player_window import VideoPlayerWidget
            opencv_player = VideoPlayerWidget(parent=container, parent_logger=self.logger)
            opencv_player.play_video(self.video_path)
            layout.addWidget(opencv_player)
            self.logger.info(f"Using OpenCV fallback for video: {self.video_path}")
        except ImportError:
            error_label = QLabel("Video playback not available (OpenCV fallback failed)")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(error_label)
            self.logger.error("OpenCV fallback not available")
        except Exception as e:
            error_label = QLabel(f"Video playback error:\n{str(e)}")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(error_label)
            self.logger.error(f"Failed to create OpenCV video player: {e}")
    
    def _on_video_state_changed(self, state):
        """Handle video state changes for PyQt5 looping"""
        if pyqt_version == 5:
            from PyQt5.QtMultimedia import QMediaPlayer
            if state == QMediaPlayer.State.StoppedState:
                # Restart for looping
                if self.video_player:
                    self.video_player.setPosition(0)
                    self.video_player.play()
    
    def _create_found_image_tab(self):
        """Create found image tab with overlays"""
        if not self.found_image_path or not os.path.exists(self.found_image_path):
            # Create placeholder if no found image
            placeholder = QLabel("Found image not available")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tab_widget.addTab(placeholder, "Found")
            return
        
        image_label = self._create_image_label(self.found_image_path, self.found_event, is_lost=False)
        self.tab_widget.addTab(image_label, "Found")
        
        # Set found tab as active if video is not available
        if not self.video_path:
            self.tab_widget.setCurrentIndex(0)
    
    def _create_lost_image_tab(self):
        """Create lost image tab with overlays"""
        if not self.lost_image_path:
            return
        
        image_label = self._create_image_label(self.lost_image_path, self.lost_event, is_lost=True)
        self.tab_widget.addTab(image_label, "Lost")
    
    def _get_bbox_and_zone_from_event(self, event_data: dict, is_lost: bool = False):
        """Extract bounding box and zone coordinates from event data based on event type
        
        Uses EventMetadataExtractor to handle different data formats from DB and JSON sources.
        """
        return EventMetadataExtractor.get_bbox_and_zone(event_data, is_lost)
    
    def _create_image_label(self, image_path: str, event_data: dict, is_lost: bool = False):
        """Create QLabel with image and overlays"""
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setScaledContents(False)
        
        # Load image
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            label.setText(f"Image not found:\n{image_path}")
            return label
        
        # Get bounding box and zone coords based on event type
        box, zone_coords = self._get_bbox_and_zone_from_event(event_data, is_lost)
        
        self.logger.debug(f"_create_image_label: image_path={image_path}, event_type={event_data.get('event_type') if event_data else None}, "
                         f"is_lost={is_lost}, has_box={box is not None}, has_zone_coords={zone_coords is not None}")
        
        # Try to resolve frame path for correct bbox normalization (use original frame size, not preview)
        frame_path = self._resolve_frame_path_for_normalization(image_path)
        bbox_img_w = pixmap.width()
        bbox_img_h = pixmap.height()
        
        if frame_path and os.path.exists(frame_path):
            try:
                frame_pixmap = QPixmap(frame_path)
                if not frame_pixmap.isNull():
                    bbox_img_w = frame_pixmap.width()
                    bbox_img_h = frame_pixmap.height()
                    self.logger.debug(f"_create_image_label: using frame dimensions for normalization: {bbox_img_w}x{bbox_img_h}")
            except Exception:
                pass
        
        # Compute target size (fit to window)
        win_w, win_h = 1200, 800
        img_w, img_h = pixmap.width(), pixmap.height()
        scale = min(win_w / img_w, win_h / img_h)
        draw_w = int(img_w * scale)
        draw_h = int(img_h * scale)
        draw_x = (win_w - draw_w) // 2
        draw_y = (win_h - draw_h) // 2
        
        # Create canvas
        canvas = QPixmap(win_w, win_h)
        canvas.fill(QColor(0, 0, 0))
        painter = QPainter()
        try:
            painter.begin(canvas)
            # Draw image
            painter.drawPixmap(draw_x, draw_y, draw_w, draw_h, pixmap)
            
            # Draw overlays
            if box:
                # Normalize bbox using EventMetadataExtractor
                normalized_bbox = EventMetadataExtractor.normalize_bbox_for_display(box, bbox_img_w, bbox_img_h)
                if normalized_bbox:
                    x1, y1, x2, y2 = normalized_bbox
                    pen = QPen(QColor(0, 255, 0), 2)
                    painter.setPen(pen)
                    x = draw_x + int(x1 * draw_w)
                    y = draw_y + int(y1 * draw_h)
                    w = int((x2 - x1) * draw_w)
                    h = int((y2 - y1) * draw_h)
                    painter.drawRect(x, y, w, h)
            
            if zone_coords:
                # Normalize zone coords using EventMetadataExtractor
                normalized_zone = EventMetadataExtractor.normalize_zone_coords(zone_coords, bbox_img_w, bbox_img_h)
                if normalized_zone:
                    pen = QPen(QColor(255, 0, 0), 2)
                    painter.setPen(pen)
                    painter.setBrush(QBrush(QColor(255, 0, 0, 64)))
                    polygon = QPolygonF()
                    for pt in normalized_zone:
                        px, py = pt  # Already normalized to [0,1] by EventMetadataExtractor
                        x = draw_x + int(px * draw_w)
                        y = draw_y + int(py * draw_h)
                        polygon.append(QPointF(x, y))
                    if polygon.count() > 0:
                        painter.drawPolygon(polygon)
        finally:
            if painter.isActive():
                painter.end()
        
        label.setPixmap(canvas)
        return label
    
    def _resolve_frame_path_for_normalization(self, preview_path: str) -> Optional[str]:
        """Resolve preview path to original frame path for correct bbox normalization"""
        if not preview_path or 'preview' not in preview_path.lower():
            return None
        
        # Try various replacements to find frame image
        candidates = []
        
        # New structure: FoundPreviews -> FoundFrames, LostPreviews -> LostFrames
        if 'FoundPreviews' in preview_path:
            candidates.append(preview_path.replace('FoundPreviews', 'FoundFrames').replace('_preview.', '_frame.'))
        elif 'LostPreviews' in preview_path:
            candidates.append(preview_path.replace('LostPreviews', 'LostFrames').replace('_preview.', '_frame.'))
        
        # Generic replacements
        candidates.append(preview_path.replace('previews', 'frames').replace('_preview.', '_frame.'))
        candidates.append(preview_path.replace('found_previews', 'found_frames').replace('_preview.', '_frame.'))
        candidates.append(preview_path.replace('lost_previews', 'lost_frames').replace('_preview.', '_frame.'))
        
        # Check candidates
        for cand in candidates:
            if cand and os.path.exists(cand):
                return cand
        
        return None
    
    def _normalize_bbox_with_size(self, box, img_w: int, img_h: int) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """Normalize bounding box to [0,1] range using image dimensions"""
        if not box or img_w <= 0 or img_h <= 0:
            return None, None, None, None
        
        try:
            if isinstance(box, dict):
                x = box.get('x', 0)
                y = box.get('y', 0)
                w = box.get('width', 0)
                h = box.get('height', 0)
                if max(x, y, w, h) <= 1.0:
                    return x, y, x + w, y + h
                else:
                    return x / img_w, y / img_h, (x + w) / img_w, (y + h) / img_h
            elif isinstance(box, (list, tuple)) and len(box) == 4:
                a, b, c, d = box
                if max(a, b, c, d) <= 1.0:
                    return a, b, c, d
                else:
                    # Assume [x, y, w, h] in pixels
                    return a / img_w, b / img_h, (a + c) / img_w, (b + d) / img_h
        except Exception:
            pass
        
        return None, None, None, None
    
    def _normalize_bbox(self, box, pixmap: QPixmap) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """Normalize bounding box to [0,1] range"""
        if not box:
            return None, None, None, None
        
        try:
            img_w, img_h = pixmap.width(), pixmap.height()
            if img_w <= 0 or img_h <= 0:
                return None, None, None, None
            
            if isinstance(box, dict):
                x = box.get('x', 0)
                y = box.get('y', 0)
                w = box.get('width', 0)
                h = box.get('height', 0)
                if max(x, y, w, h) <= 1.0:
                    return x, y, x + w, y + h
                else:
                    return x / img_w, y / img_h, (x + w) / img_w, (y + h) / img_h
            elif isinstance(box, (list, tuple)) and len(box) == 4:
                a, b, c, d = box
                if max(a, b, c, d) <= 1.0:
                    return a, b, c, d
                else:
                    # Assume [x, y, w, h] in pixels
                    return a / img_w, b / img_h, (a + c) / img_w, (b + d) / img_h
        except Exception:
            pass
        
        return None, None, None, None
    
    def closeEvent(self, event):
        """Handle window close event - stop video playback"""
        if self.video_player:
            try:
                self.video_player.stop()
            except Exception:
                pass
        super().closeEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        self.hide()
        event.accept()

    def _normalize_bbox(self, box, pixmap: QPixmap) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """Normalize bounding box to [0,1] range"""
        if not box:
            return None, None, None, None
        
        try:
            img_w, img_h = pixmap.width(), pixmap.height()
            if img_w <= 0 or img_h <= 0:
                return None, None, None, None
            
            if isinstance(box, dict):
                x = box.get('x', 0)
                y = box.get('y', 0)
                w = box.get('width', 0)
                h = box.get('height', 0)
                if max(x, y, w, h) <= 1.0:
                    return x, y, x + w, y + h
                else:
                    return x / img_w, y / img_h, (x + w) / img_w, (y + h) / img_h
            elif isinstance(box, (list, tuple)) and len(box) == 4:
                a, b, c, d = box
                if max(a, b, c, d) <= 1.0:
                    return a, b, c, d
                else:
                    # Assume [x, y, w, h] in pixels
                    return a / img_w, b / img_h, (a + c) / img_w, (b + d) / img_h
        except Exception:
            pass
        
        return None, None, None, None

    def mouseDoubleClickEvent(self, event):
        self.hide()
        event.accept()
