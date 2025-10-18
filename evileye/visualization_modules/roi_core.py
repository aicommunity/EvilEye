from typing import List, Tuple, Optional

try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox,
        QSpinBox, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
        QGraphicsPixmapItem, QFrame
    )
    from PyQt6.QtCore import Qt, pyqtSignal, QTimer
    from PyQt6.QtGui import QPixmap, QImage, QPen, QColor, QPalette, QBrush, QCursor
    from PyQt6.QtCore import QPointF, QRectF, QPoint
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox,
        QSpinBox, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
        QGraphicsPixmapItem, QFrame
    )
    from PyQt5.QtCore import Qt, pyqtSignal, QTimer
    from PyQt5.QtGui import QPixmap, QImage, QPen, QColor, QPalette, QBrush, QCursor
    from PyQt5.QtCore import QPointF, QRectF, QPoint
    pyqt_version = 5

from ..core.logger import get_module_logger
try:
    import sip  # For checking deleted Qt wrappers
except Exception:
    sip = None


class ResizeHandle(QGraphicsRectItem):
    def __init__(self, x, y, size, parent=None):
        super().__init__(x, y, size, size, parent)
        self.setPen(QPen(Qt.GlobalColor.yellow, 2))
        self.setBrush(QBrush(Qt.GlobalColor.yellow))
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(1000)
        self.parent_view = None
        self.parent_roi = None
        self.handle_index = -1

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
            if self.parent_view:
                self.parent_view.resizing = True
                self.parent_view.resize_handle = self
            event.accept()
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.parent_roi and self.parent_view:
            scene_pos = self.mapToScene(event.pos())
            if hasattr(self.parent_view, '_update_roi_size'):
                self.parent_view._update_roi_size(scene_pos, self)
        event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        if self.parent_view:
            self.parent_view.resizing = False
            self.parent_view.resize_handle = None
        event.accept()
        super().mouseReleaseEvent(event)

    def hoverEnterEvent(self, event):
        self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        super().hoverLeaveEvent(event)


class ROIGraphicsView(QGraphicsView):
    roi_selected = pyqtSignal(dict)
    roi_added = pyqtSignal(list)
    roi_removed = pyqtSignal(int)
    roi_updated = pyqtSignal(int, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundRole(QPalette.ColorRole.Dark)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self.rois = []
        self.roi_data = []
        self.selected_roi = None
        self.selected_roi_id = -1
        self.drawing = False
        self.start_point = None
        self.temp_rect = None

        self.roi_state = {'selected_id': -1, 'hovered_id': -1, 'resizing_id': -1, 'drawing': False}

        self.red_pen = QPen(Qt.GlobalColor.red, 2)
        self.green_pen = QPen(Qt.GlobalColor.green, 2, Qt.PenStyle.DashLine)
        self.selected_pen = QPen(Qt.GlobalColor.blue, 3)

        self.original_size = None
        self.display_size = None
        self.scale_factor = 1.0
        self.pixmap_item = None

        self.resize_handles = []
        self.resize_handle_size = 8
        self.resizing = False
        self.resize_handle = None

        self.scale_to_original = None
        self.source_to_display_scale = None

        self.user_scaled = False
        self.auto_fit_enabled = True

        self.base_line_width = 4
        self.handle_size = 20
        self.selected_line_multiplier = 2.0

        self.logger = get_module_logger("roi_graphics_view")

    def add_pixmap(self, pixmap: QPixmap) -> bool:
        try:
            self.scene.clear()
            self.rois.clear()
            self.roi_data.clear()
            self.selected_roi = None

            self.original_size = (pixmap.width(), pixmap.height())
            self.display_size = (pixmap.width(), pixmap.height())
            self.scale_factor = 1.0

            self.pixmap_item = QGraphicsPixmapItem(pixmap)
            self.scene.addItem(self.pixmap_item)
            view_origin = self.mapToScene(QPoint(0, 0))
            self.pixmap_item.setPos(view_origin)
            self.scene.setSceneRect(view_origin.x(), view_origin.y(),
                                    self.pixmap_item.boundingRect().width(),
                                    self.pixmap_item.boundingRect().height())
            self.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
            self.centerOn(self.pixmap_item.pos())
            return True
        except Exception:
            return False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            items = self.scene.items(scene_pos)
            for item in items:
                if item in self.resize_handles:
                    self.resizing = True
                    self.resize_handle = item
                    self.set_roi_state(resizing_id=self.get_selected_roi_id())
                    event.accept()
                    return
            roi_items = [item for item in items if isinstance(item, QGraphicsRectItem) and item in self.rois]
            if roi_items:
                roi_items.sort(key=lambda x: x.rect().width() * x.rect().height())
                selected_roi = roi_items[0]
                self._select_roi(selected_roi)
                event.accept()
                return
            self.drawing = True
            self.start_point = scene_pos
            self.set_roi_state(drawing=True)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        if self.resizing and self.resize_handle and self.selected_roi:
            self._update_roi_size(scene_pos, self.resize_handle)
            event.accept()
        elif self.drawing and self.start_point:
            self._draw_temp_roi(scene_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        if event.button() == Qt.MouseButton.LeftButton:
            if self.resizing:
                self._finish_resizing()
                event.accept()
                return
            elif self.drawing:
                self._finish_drawing(scene_pos)
                event.accept()

    def wheelEvent(self, event):
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor
        if event.angleDelta().y() > 0:
            self.scale(zoom_in_factor, zoom_in_factor)
        else:
            self.scale(zoom_out_factor, zoom_out_factor)
        self.user_scaled = True
        self._update_all_roi_pens()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.pixmap_item is not None and self.auto_fit_enabled:
            if not self.user_scaled:
                QTimer.singleShot(0, self._delayed_fit_in_view)
            self._update_all_roi_pens()

    def _delayed_fit_in_view(self):
        if self.pixmap_item is not None:
            self.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
            self.centerOn(self.pixmap_item.pos())

    def _draw_temp_roi(self, scene_pos):
        if self.temp_rect:
            self.scene.removeItem(self.temp_rect)
        rect = QRectF(self.start_point, scene_pos).normalized()
        pen_width = self._get_scaled_pen_width()
        temp_pen = QPen(Qt.GlobalColor.green, pen_width, Qt.PenStyle.DashLine)
        self.temp_rect = self.scene.addRect(rect, temp_pen)

    def _finish_resizing(self):
        self.resizing = False
        self.resize_handle = None
        self.set_roi_state(resizing_id=-1)
        if self.selected_roi:
            self._add_resize_handles(self.selected_roi)

    def _finish_drawing(self, scene_pos):
        if self.temp_rect:
            self.scene.removeItem(self.temp_rect)
            self.temp_rect = None
        rect = QRectF(self.start_point, scene_pos).normalized()
        if rect.width() > 10 and rect.height() > 10:
            # Преобразуем координаты сцены в координаты отображения (с учётом смещения pixmap)
            if self.pixmap_item is not None:
                pixmap_pos = self.pixmap_item.pos()
                display_x1 = int(rect.x() - pixmap_pos.x())
                display_y1 = int(rect.y() - pixmap_pos.y())
                # Qt прямоугольник: правая/нижняя граница включительно => x + width - 1
                display_x2 = int(rect.x() + rect.width() - 1 - pixmap_pos.x())
                display_y2 = int(rect.y() + rect.height() - 1 - pixmap_pos.y())
            else:
                display_x1 = int(rect.x())
                display_y1 = int(rect.y())
                display_x2 = int(rect.x() + rect.width() - 1)
                display_y2 = int(rect.y() + rect.height() - 1)

            # Ограничим координаты размером изображения, если известен
            if self.original_size:
                image_width, image_height = self.original_size
                display_x1 = max(0, min(display_x1, image_width))
                display_y1 = max(0, min(display_y1, image_height))
                display_x2 = max(0, min(display_x2, image_width))
                display_y2 = max(0, min(display_y2, image_height))

            display_coords = [display_x1, display_y1, display_x2, display_y2]
            source_coords = self._convert_display_to_source_coords(display_coords) or display_coords
            if source_coords:
                roi_item = self.add_roi(source_coords, (255, 0, 0))
                if roi_item:
                    self._select_roi(roi_item)
        self.drawing = False
        self.start_point = None
        self.set_roi_state(drawing=False)

    def _select_roi(self, roi_item):
        self.deselect_roi()
        self.selected_roi = roi_item
        self.selected_roi_id = self.rois.index(roi_item)
        self.set_roi_state(selected_id=self.selected_roi_id)
        pen_width = self._get_scaled_pen_width()
        selected_pen = QPen(QColor(255, 100, 100), pen_width * self.selected_line_multiplier)
        roi_item.setPen(selected_pen)
        self._add_resize_handles(roi_item)
        try:
            roi_info = self.roi_data[self.selected_roi_id]
            self.roi_selected.emit(roi_info)
        except (ValueError, IndexError):
            pass

    def deselect_roi(self):
        if self.selected_roi:
            self._remove_resize_handles()
            roi_id = self.selected_roi_id
            if roi_id >= 0:
                original_color = self.get_roi_data_by_id(roi_id).get("color", (255, 0, 0))
                pen_width = self._get_scaled_pen_width()
                if isinstance(original_color, tuple) and len(original_color) == 3:
                    normal_pen = QPen(QColor(*original_color), pen_width)
                else:
                    normal_pen = QPen(Qt.GlobalColor.red, pen_width)
                self.selected_roi.setPen(normal_pen)
            self.selected_roi = None
            self.set_roi_state(selected_id=-1)
            self.selected_roi_id = -1

    def add_roi(self, coords: List[int], color: Tuple[int, int, int] = (255, 0, 0)):
        roi_item = self._create_roi_item(coords, color)
        if roi_item:
            self.rois.append(roi_item)
            self.roi_data.append({"coords": coords, "color": color})
            self.scene.update()
            self.roi_added.emit(coords)
            return roi_item
        return None

    def add_roi_direct(self, coords: List[int], color: Tuple[int, int, int] = (255, 0, 0)):
        try:
            roi_item = self._create_roi_item(coords, color)
            if roi_item:
                self.rois.append(roi_item)
                # Добавляем в roi_data только если это не загрузка из конфига
                if not hasattr(self, '_loading_from_config') or not self._loading_from_config:
                    self.roi_data.append({"coords": coords, "color": color})
                # Безопасное обновление сцены
                try:
                    self.scene.update()
                except Exception as e:
                    self.logger.error(f"Error updating scene: {e}")
                # Испускаем сигнал для обновления списка (только если это не загрузка из конфига)
                if not hasattr(self, '_loading_from_config') or not self._loading_from_config:
                    self.roi_added.emit(coords)
                return roi_item
            return None
        except Exception as e:
            self.logger.error(f"Error in add_roi_direct: {e}")
            return None

    def remove_roi(self, index: int):
        if 0 <= index < len(self.rois):
            roi_item = self.rois[index]
            self.scene.removeItem(roi_item)
            del self.rois[index]
            del self.roi_data[index]
            self.roi_removed.emit(index)

    def clear_rois(self):
        for roi_item in self.rois:
            self.scene.removeItem(roi_item)
        self.rois.clear()
        self.roi_data.clear()
        self.selected_roi = None

    def update_roi(self, index: int, coords: List[int]):
        if 0 <= index < len(self.rois) and len(coords) == 4:
            old_roi_item = self.rois[index]
            self.scene.removeItem(old_roi_item)
            x1, y1, x2, y2 = coords
            rect = QRectF(x1, y1, x2 - x1, y2 - y1)
            roi_area = rect.width() * rect.height()
            z_value = 1000 - int(roi_area / 1000)
            new_roi_item = self.scene.addRect(rect, self.red_pen)
            new_roi_item.setZValue(z_value)
            self.rois[index] = new_roi_item
            self.roi_data[index]["coords"] = coords
            if self.selected_roi == old_roi_item:
                self.selected_roi = new_roi_item
                new_roi_item.setPen(self.selected_pen)

    def get_rois(self) -> List[dict]:
        return [{"coords": roi["coords"]} for roi in self.roi_data]

    def _create_roi_item(self, coords, color):
        if len(coords) == 4:
            display_coords = self._convert_source_to_display_coords(coords)
            if display_coords:
                display_x1, display_y1, display_x2, display_y2 = display_coords
                if self.pixmap_item is not None:
                    pixmap_pos = self.pixmap_item.pos()
                    scene_x1 = display_x1 + pixmap_pos.x()
                    scene_y1 = display_y1 + pixmap_pos.y()
                    scene_x2 = display_x2 + pixmap_pos.x()
                    scene_y2 = display_y2 + pixmap_pos.y()
                    rect = QRectF(scene_x1, scene_y1, scene_x2 - scene_x1, scene_y2 - scene_y1)
                else:
                    rect = QRectF(display_x1, display_y1, display_x2 - display_x1, display_y2 - display_y1)
                pen_width = self._get_scaled_pen_width()
                pen = QPen(QColor(*color), pen_width) if isinstance(color, tuple) and len(color) == 3 else QPen(Qt.GlobalColor.red, pen_width)
                roi_area = rect.width() * rect.height()
                z_value = 1000 - int(roi_area / 1000)
                try:
                    rect_item = self.scene.addRect(rect, pen)
                    rect_item.setZValue(z_value)
                    return rect_item
                except Exception as e:
                    self.logger.error(f"Error creating ROI item: {e}")
                    return None
        return None

    def _get_scaled_pen_width(self, base_width=None):
        if base_width is None:
            base_width = self.base_line_width
        transform = self.transform()
        scale_factor = transform.m11()
        target_screen_width = base_width
        pen_width = max(1, target_screen_width / scale_factor)
        return pen_width

    def _update_all_roi_pens(self):
        pen_width = self._get_scaled_pen_width()
        for roi_item in self.rois:
            pen = roi_item.pen()
            pen.setWidthF(pen_width)
            roi_item.setPen(pen)
        if self.selected_roi:
            selected_pen = self.selected_roi.pen()
            selected_pen.setWidthF(pen_width * self.selected_line_multiplier)
            self.selected_roi.setPen(selected_pen)

    def _add_resize_handles(self, roi_item):
        self._remove_resize_handles()
        rect = roi_item.rect()
        handle_size = self.handle_size
        positions = [
            (rect.left(), rect.top()),
            (rect.center().x(), rect.top()),
            (rect.right(), rect.top()),
            (rect.right(), rect.center().y()),
            (rect.right(), rect.bottom()),
            (rect.center().x(), rect.bottom()),
            (rect.left(), rect.bottom()),
            (rect.left(), rect.center().y()),
        ]
        for i, pos in enumerate(positions):
            handle = ResizeHandle(pos[0] - handle_size/2, pos[1] - handle_size/2, handle_size)
            handle.handle_index = i
            handle.parent_roi = roi_item
            handle.parent_view = self
            # Привязываем маркер как дочерний к ROI, чтобы управлять жизненным циклом безопаснее
            try:
                handle.setParentItem(roi_item)
            except Exception:
                pass
            self.resize_handles.append(handle)

    def _remove_resize_handles(self):
        # Удаляем маркеры безопасно, учитывая возможное удаление Qt-обёрток
        for handle in list(self.resize_handles):
            try:
                if handle is None:
                    continue
                if sip is not None:
                    try:
                        if sip.isdeleted(handle):
                            continue
                    except Exception:
                        pass
                # Отвязываем от родителя, затем удаляем из сцены при наличии
                try:
                    handle.setParentItem(None)
                except Exception:
                    pass
                try:
                    sc = handle.scene()
                    if sc is not None:
                        sc.removeItem(handle)
                except RuntimeError:
                    pass
                except Exception:
                    pass
            except Exception:
                pass
        self.resize_handles.clear()

    def ensure_rois_visible(self):
        if not self.rois:
            return
        first_roi = self.rois[0]
        bounding_rect = first_roi.rect()
        for roi in self.rois[1:]:
            bounding_rect = bounding_rect.united(roi.rect())
        margin = 50
        bounding_rect = bounding_rect.adjusted(-margin, -margin, margin, margin)
        current_scene_rect = self.scene.sceneRect()
        new_scene_rect = current_scene_rect.united(bounding_rect)
        self.scene.setSceneRect(new_scene_rect)
        self.fitInView(bounding_rect, Qt.AspectRatioMode.KeepAspectRatio)
        self.centerOn(bounding_rect.center())

    def _convert_source_to_display_coords(self, source_coords):
        if len(source_coords) != 4:
            return None
        x1, y1, x2, y2 = source_coords
        if self.source_to_display_scale is None:
            return source_coords
        display_x1 = int(x1 * self.source_to_display_scale['scale_x'])
        display_y1 = int(y1 * self.source_to_display_scale['scale_y'])
        display_x2 = int(x2 * self.source_to_display_scale['scale_x'])
        display_y2 = int(y2 * self.source_to_display_scale['scale_y'])
        return [display_x1, display_y1, display_x2, display_y2]

    def _convert_display_to_source_coords(self, display_coords):
        if len(display_coords) != 4:
            return None
        x1, y1, x2, y2 = display_coords
        if self.source_to_display_scale is None:
            return display_coords
        source_x1 = int(x1 / self.source_to_display_scale['scale_x'])
        source_y1 = int(y1 / self.source_to_display_scale['scale_y'])
        source_x2 = int(x2 / self.source_to_display_scale['scale_x'])
        source_y2 = int(y2 / self.source_to_display_scale['scale_y'])
        return [source_x1, source_y1, source_x2, source_y2]

    def get_selected_roi_id(self):
        return self.roi_state['selected_id']

    def set_roi_state(self, **kwargs):
        for key, value in kwargs.items():
            if key in self.roi_state:
                self.roi_state[key] = value

    def select_roi_by_index(self, index: int):
        """Совместимость со старым API: выбрать ROI по индексу."""
        return self._select_by_index(index)

    def _select_by_index(self, index: int):
        if 0 <= index < len(self.rois):
            self._select_roi(self.rois[index])
            return True
        return False

    def get_roi_by_id(self, roi_id):
        if 0 <= roi_id < len(self.rois):
            return self.rois[roi_id]
        return None

    def get_roi_data_by_id(self, roi_id):
        if 0 <= roi_id < len(self.roi_data):
            return self.roi_data[roi_id]
        return None

    def _update_roi_size(self, scene_pos, handle=None):
        if not self.selected_roi:
            return
        if handle:
            self.resize_handle = handle
        elif not self.resize_handle:
            return
        current_rect = self.selected_roi.rect().normalized()
        handle_index = getattr(self.resize_handle, 'handle_index', None)
        if handle_index is None:
            return
        new_rect = current_rect
        if handle_index == 0:
            new_rect.setTopLeft(scene_pos)
        elif handle_index == 1:
            new_rect.setTop(scene_pos.y())
        elif handle_index == 2:
            new_rect.setTopRight(scene_pos)
        elif handle_index == 3:
            new_rect.setRight(scene_pos.x())
        elif handle_index == 4:
            new_rect.setBottomRight(scene_pos)
        elif handle_index == 5:
            new_rect.setBottom(scene_pos.y())
        elif handle_index == 6:
            new_rect.setBottomLeft(scene_pos)
        elif handle_index == 7:
            new_rect.setLeft(scene_pos.x())
        new_rect = new_rect.normalized()
        self.selected_roi.setRect(new_rect)
        try:
            index = self.rois.index(self.selected_roi)
            if self.pixmap_item is not None:
                pixmap_pos = self.pixmap_item.pos()
                display_x1 = int(new_rect.x() - pixmap_pos.x())
                display_y1 = int(new_rect.y() - pixmap_pos.y())
                # Прямоугольник Qt задаёт правую/нижнюю границу как x + width - 1 (включительно)
                display_x2 = int(new_rect.x() + new_rect.width() - 1 - pixmap_pos.x())
                display_y2 = int(new_rect.y() + new_rect.height() - 1 - pixmap_pos.y())
                if self.original_size:
                    image_width, image_height = self.original_size
                    display_x1 = max(0, min(display_x1, image_width))
                    display_y1 = max(0, min(display_y1, image_height))
                    display_x2 = max(0, min(display_x2, image_width))
                    display_y2 = max(0, min(display_y2, image_height))
                display_coords = [display_x1, display_y1, display_x2, display_y2]
                source_coords = self._convert_display_to_source_coords(display_coords) or display_coords
                self.roi_data[index]["coords"] = source_coords
                self.roi_updated.emit(index, source_coords)
            else:
                display_coords = [int(new_rect.x()), int(new_rect.y()), int(new_rect.x() + new_rect.width()), int(new_rect.y() + new_rect.height())]
                self.roi_data[index]["coords"] = display_coords
                self.roi_updated.emit(index, display_coords)
        except ValueError:
            pass


class ROICoordsDialog(QDialog):
    def __init__(self, parent: Optional[object] = None, coords: Optional[List[int]] = None):
        super().__init__(parent)
        self.setWindowTitle("Edit ROI")
        self.setModal(True)
        self.resize(300, 200)
        self.logger = get_module_logger("roi_coords_dialog")
        self.coords = coords or [0, 0, 100, 100]
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.x1_spin = QSpinBox(); self.x1_spin.setRange(0, 10000); self.x1_spin.setValue(self.coords[0]); form_layout.addRow("X1:", self.x1_spin)
        self.y1_spin = QSpinBox(); self.y1_spin.setRange(0, 10000); self.y1_spin.setValue(self.coords[1]); form_layout.addRow("Y1:", self.y1_spin)
        self.x2_spin = QSpinBox(); self.x2_spin.setRange(0, 10000); self.x2_spin.setValue(self.coords[2]); form_layout.addRow("X2:", self.x2_spin)
        self.y2_spin = QSpinBox(); self.y2_spin.setRange(0, 10000); self.y2_spin.setValue(self.coords[3]); form_layout.addRow("Y2:", self.y2_spin)
        layout.addLayout(form_layout)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept); button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_coords(self) -> Optional[List[int]]:
        x1 = self.x1_spin.value(); y1 = self.y1_spin.value(); x2 = self.x2_spin.value(); y2 = self.y2_spin.value()
        if x1 >= x2 or y1 >= y2:
            self.logger.warning("Invalid ROI coordinates")
            return None
        return [x1, y1, x2, y2]


