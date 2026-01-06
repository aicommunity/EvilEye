"""
Унифицированные компоненты для журналов (делегаты, окна изображений)
Работают с любым источником данных (БД или JSON)
"""

import os
import datetime
from typing import Optional, List, Tuple

try:
    from PyQt6.QtCore import Qt, QSize, QPointF, QRect
    from PyQt6.QtWidgets import QStyledItemDelegate, QLabel, QVBoxLayout, QTableWidget
    from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QPolygonF
    pyqt_version = 6
except ImportError:
    from PyQt5.QtCore import Qt, QSize, QPointF, QRect
    from PyQt5.QtWidgets import QStyledItemDelegate, QLabel, QVBoxLayout, QTableWidget
    from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QPolygonF
    pyqt_version = 5

from ..core.logger import get_module_logger
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
            self._draw_overlays_from_data(painter, box, zone_coords, draw_x, draw_y, draw_w, draw_h)
        
        # Get video paths for events journal (independent of Found/Lost buttons)
        found_video_path = preview_data.get('found_video_path') if self.journal_type == 'events' else None
        lost_video_path = preview_data.get('lost_video_path') if self.journal_type == 'events' else None
        current_video_path = found_video_path if current_mode == 'found' else lost_video_path
        
        # Draw switching buttons if both found and lost paths are available
        found_path = preview_data.get('found_path', '')
        lost_path = preview_data.get('lost_path', '')
        has_both_previews = bool(found_path and lost_path)
        
        # Draw Found/Lost buttons only if both previews exist
        if has_both_previews:
            self._draw_switching_buttons(painter, option, current_mode, draw_x, draw_y, draw_w, draw_h, 
                                        current_video_path if self.journal_type == 'events' else None, 
                                        has_found_lost=True)
        # Draw Play/Stop button independently if video is available (even without Found/Lost buttons)
        elif self.journal_type == 'events' and current_video_path:
            self._draw_switching_buttons(painter, option, current_mode, draw_x, draw_y, draw_w, draw_h,
                                        current_video_path, has_found_lost=False)
    
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

    def _draw_switching_buttons(self, painter, option, current_mode, draw_x, draw_y, draw_w, draw_h, video_path=None, has_found_lost=True):
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
                # Check if video is currently playing
                is_playing = False
                if self.journal_widget and self.journal_widget.video_player:
                    is_playing = getattr(self.journal_widget.video_player, '_is_playing', False)
                
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
        
        # Draw overlays if available
        if box or zone_coords:
            self._draw_overlays_from_data(painter, box, zone_coords, draw_x, draw_y, draw_w, draw_h)
    
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
                # Check if video is currently playing
                is_playing = False
                if self.journal_widget.video_player:
                    is_playing = getattr(self.journal_widget.video_player, '_is_playing', False)
                
                if is_playing:
                    # Stop video playback
                    if self.journal_widget.video_player:
                        self.journal_widget.video_player.stop()
                        # Widget will be removed in _on_video_stopped
                    return True
                else:
                    # Start video playback
                    # Stop any existing video playback
                    if self.journal_widget.video_player:
                        self.journal_widget.video_player.stop()
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
                    
                    row = index.row()
                    col = index.column()
                    
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
                    self.journal_widget.video_player.stopped.connect(self._on_video_stopped)
                    
                    # Set widget in cell - this will show video over the image
                    table.setCellWidget(row, col, self.journal_widget.video_player)
                    
                    # Start playback
                    if self.journal_widget.video_player.play_video(current_video_path):
                        # Store row/col for cleanup
                        self.journal_widget._video_player_row = row
                        self.journal_widget._video_player_col = col
                    else:
                        # Playback failed, remove widget
                        table.setCellWidget(row, col, None)
                        self.journal_widget.video_player = None
                    
                    return True

        # Handle Found/Lost buttons (only if both previews exist)
        if has_both_previews and found_rect and found_rect.contains(click_pos):
            # Clicked on Found button
            # Stop video playback if active
            if self.journal_widget and self.journal_widget.video_player:
                self.journal_widget.video_player.stop()
                # Widget will be removed in _on_video_stopped
            
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
            # Stop video playback if active
            if self.journal_widget and self.journal_widget.video_player:
                self.journal_widget.video_player.stop()
                # Widget will be removed in _on_video_stopped
            
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
        if self.journal_widget and self.journal_widget.video_player:
            # Remove widget from cell
            table = self.parent()
            if table and isinstance(table, QTableWidget):
                row = getattr(self.journal_widget, '_video_player_row', None)
                col = getattr(self.journal_widget, '_video_player_col', None)
                if row is not None and col is not None:
                    # Store reference before clearing
                    widget_to_remove = self.journal_widget.video_player
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
                # Clear reference if no table
                self.journal_widget.video_player = None
            # Clean up stored coordinates
            if hasattr(self.journal_widget, '_video_player_row'):
                delattr(self.journal_widget, '_video_player_row')
            if hasattr(self.journal_widget, '_video_player_col'):
                delattr(self.journal_widget, '_video_player_col')

    def _resolve_image_path(self, img_path: str, date_folder: str = '') -> Optional[str]:
        """Resolve image path to full absolute path"""
        if not img_path:
            return None
        
        # Already absolute
        if os.path.isabs(img_path):
            return img_path if os.path.exists(img_path) else None
        
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

    def _draw_overlays(self, painter, event_data: dict, draw_x: int, draw_y: int, 
                      draw_w: int, draw_h: int, img_path: str):
        """Draw bounding box and zone overlays from event data"""
        box = event_data.get('bounding_box') or event_data.get('box')
        zone_coords = event_data.get('zone_coords')
        self._draw_overlays_from_data(painter, box, zone_coords, draw_x, draw_y, draw_w, draw_h)
    
    def _draw_overlays_from_data(self, painter, box, zone_coords, draw_x: int, draw_y: int, 
                                  draw_w: int, draw_h: int):
        """Draw bounding box and zone overlays from box and zone_coords data"""
        # Draw bounding box
        if box and len(box) == 4:
            painter.setPen(QPen(QColor(0, 255, 0), 2))  # Green for bbox
            # Coordinates are normalized [x1, y1, x2, y2]
            x1, y1, x2, y2 = box
            x = draw_x + int(x1 * draw_w)
            y = draw_y + int(y1 * draw_h)
            w = int((x2 - x1) * draw_w)
            h = int((y2 - y1) * draw_h)
            painter.drawRect(x, y, w, h)
        
        # Draw zone
        if zone_coords:
            painter.setPen(QPen(QColor(255, 0, 0), 2))  # Red for zone
            painter.setBrush(QBrush(QColor(255, 0, 0, 64)))  # Semi-transparent red fill
            polygon = QPolygonF()
            for pt in zone_coords:
                if isinstance(pt, (list, tuple)) and len(pt) == 2:
                    px, py = pt
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


class UnifiedImageWindow(QLabel):
    """Универсальное окно для просмотра изображений с оверлеями"""
    
    def __init__(self, image_path: str, box=None, zone_coords=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Image')
        try:
            self.setWindowFlag(Qt.Window, True)
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        except Exception:
            pass
        self.setFixedSize(900, 600)
        self.image_path = image_path
        self.zone_coords = zone_coords
        
        # Load image
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            self.label = QLabel(f"Image not found:\n{image_path}")
            self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout = QVBoxLayout()
            self.layout.addWidget(self.label)
            self.setLayout(self.layout)
            return
            
        # Compute target rect in window
        win_w, win_h = self.width(), self.height()
        img_w, img_h = pixmap.width(), pixmap.height()
        scale = min(win_w / img_w, win_h / img_h)
        draw_w = int(img_w * scale)
        draw_h = int(img_h * scale)
        draw_x = (win_w - draw_w) // 2
        draw_y = (win_h - draw_h) // 2

        # Create canvas pixmap sized to window
        canvas = QPixmap(win_w, win_h)
        canvas.fill(QColor(0, 0, 0))
        painter = QPainter()
        try:
            painter.begin(canvas)
            # Draw image
            painter.drawPixmap(draw_x, draw_y, draw_w, draw_h, pixmap)
            
            # Draw overlays
            if box:
                pen = QPen(QColor(0, 255, 0), 2)
                painter.setPen(pen)
                x1, y1, x2, y2 = self._normalize_bbox(box, pixmap)
                if x1 is not None:
                    x = draw_x + int(x1 * draw_w)
                    y = draw_y + int(y1 * draw_h)
                    w = int((x2 - x1) * draw_w)
                    h = int((y2 - y1) * draw_h)
                    painter.drawRect(x, y, w, h)
            
            if self.zone_coords:
                pen = QPen(QColor(255, 0, 0), 2)
                painter.setPen(pen)
                painter.setBrush(QBrush(QColor(255, 0, 0, 64)))
                polygon = QPolygonF()
                for pt in self.zone_coords:
                    if isinstance(pt, (list, tuple)) and len(pt) == 2:
                        px, py = pt
                        if max(px, py) <= 1.0:
                            x = draw_x + int(px * draw_w)
                            y = draw_y + int(py * draw_h)
                        else:
                            x = int(px)
                            y = int(py)
                        polygon.append(QPointF(x, y))
                if polygon.count() > 0:
                    painter.drawPolygon(polygon)
        finally:
            if painter.isActive():
                painter.end()
        
        # Create label and set pixmap
        self.label = QLabel()
        self.label.setPixmap(canvas)
        
        # Setup layout
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.label)
        self.setLayout(self.layout)

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
