try:
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QTabWidget, QPushButton, QGraphicsPixmapItem, QGraphicsTransform,
        QSizePolicy, QMenuBar, QToolBar, QDateTimeEdit, QHeaderView, QGraphicsView, QGraphicsScene,
        QMenu, QMainWindow, QMessageBox, QTableView, QTableWidget, QTableWidgetItem, QGraphicsRectItem,
        QGraphicsPolygonItem
    )
    from PyQt6.QtGui import QPixmap, QIcon, QAction, QPainter, QBrush, QPen, QColor, QPolygonF
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt, QPointF, QPoint, QSize, QRectF, QSizeF, QTimer


    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QTabWidget, QPushButton, QGraphicsPixmapItem, QGraphicsTransform,
        QSizePolicy, QMenuBar, QToolBar, QDateTimeEdit, QHeaderView, QGraphicsView, QGraphicsScene,
        QMenu, QMainWindow, QMessageBox, QTableView, QTableWidget, QTableWidgetItem, QGraphicsRectItem,
        QGraphicsPolygonItem
    )
    from PyQt5.QtGui import QPixmap, QIcon, QPainter, QBrush, QPen, QColor, QPolygonF
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt, QPointF, QPoint, QSize, QRectF, QSizeF, QTimer
    from PyQt5.QtWidgets import QAction

    pyqt_version = 5

from ..core.logger import get_module_logger

import sys
import os
from ..utils import utils
from ..utils import threading_events
from ..events_detectors.zone import ZoneForm


class CustomPixmapItem(QGraphicsPixmapItem):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptHoverEvents(True)
        self.circle = None

    def hoverEnterEvent(self, event):
        super().hoverEnterEvent(event)
        self.circle = self.scene().addEllipse(0, 0, 10, 10)
        self.circle.setPos(QPointF(0, 0))
        self.circle.setPen(QPen(Qt.GlobalColor.red))

    def hoverLeaveEvent(self, event):
        super().hoverLeaveEvent(event)
        self.scene().removeItem(self.circle)

    def hoverMoveEvent(self, event):
        super().hoverMoveEvent(event)
        img_pos = event.pos().toPoint()
        # На краях изображения курсор меняется для облегчения привязки при добавлении зоны
        if (img_pos.x() == 0 or img_pos.y() == 0 or
                img_pos.x() == self.pixmap().width() - 1 or img_pos.y() == self.pixmap().height() - 1):
            scene_pos = self.mapToScene(event.pos())
            self.circle.setPos(QPointF(scene_pos.x() - 5, scene_pos.y() - 5))
            self.circle.setVisible(True)
        else:
            self.circle.setVisible(False)
        event.accept()


class GraphicsView(QGraphicsView):
    # Сигналы для уведомления об изменениях зон
    zone_added = pyqtSignal()
    zone_removed = pyqtSignal()
    
    def __init__(self, parent=None, sources_zones=None, params=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.rectangle = None
        self.polygon = None
        self.polygon_coords = []
        self.pix = None
        self.source_id = None
        self.sources_zones = sources_zones
        self.params = params

        self.red_brush = QBrush(QColor(255, 0, 0, 128))
        self.red_pen = QPen(Qt.GlobalColor.red)
        self.is_rect_clicked = False
        self.is_poly_clicked = False
        self.is_rect_clicked_del = False

    def set_source_id(self, src_id):
        self.source_id = src_id
        if self.source_id not in self.sources_zones:
            self.sources_zones[src_id] = []

    def add_pixmap(self, source_id, pixmap):  # Добавление изображение в окно + отрисовка имеющихся зон
        self.source_id = source_id
        if self.source_id not in self.sources_zones:
            self.sources_zones[source_id] = []
        # Добавление изображения на сцену
        self.pix = CustomPixmapItem()
        self.pix.setPixmap(pixmap)
        self.scene.addItem(self.pix)
        view_origin = self.mapToScene(QPoint(0, 0))
        self.pix.setPos(view_origin)
        self.scene.setSceneRect(view_origin.x(), view_origin.y(),
                                self.pix.boundingRect().width(), self.pix.boundingRect().height())
        # Масштабируем изображение чтобы оно заполняло все доступное пространство
        self.fitInView(self.pix, Qt.AspectRatioMode.KeepAspectRatio)
        self.centerOn(self.pix.pos())

        self.polygon = QGraphicsPolygonItem(self.pix)
        self.polygon.setPen(self.red_pen)
        self.polygon.setBrush(self.red_brush)

        if self.source_id in self.sources_zones:
            for i in range(len(self.sources_zones[self.source_id])):
                # Отрисовка зон после каждого открытия окна
                zone_type, zone_coords, item = self.sources_zones[self.source_id][i]
                if not item:  # Для зон из json
                    coords = [QPointF(point[0] * pixmap.width(), point[1] * pixmap.height()) for point in zone_coords]
                else:
                    coords = [QPointF(point[0] * pixmap.width(), point[1] * pixmap.height()) for point in zone_coords]
                if ZoneForm(zone_type) == ZoneForm.Rectangle:
                    rect = QRectF(self.pix.mapToScene(coords[0]), self.pix.mapToScene(coords[2]))
                    scene_rect = self.scene.addRect(rect, self.red_pen, self.red_brush)
                    # Если зона была задана только координатами в json, добавляем элемент сцены для дальнейшего
                    # сравнения и удаления
                    if not item:
                        self.sources_zones[self.source_id][i][2] = scene_rect.boundingRect()
                elif ZoneForm(zone_type) == ZoneForm.Polygon:
                    polygon = QGraphicsPolygonItem(self.pix)
                    polygon.setPen(self.red_pen)
                    polygon.setBrush(self.red_brush)
                    poly = QPolygonF(coords)
                    polygon.setPolygon(poly)
                    if not item:
                        self.sources_zones[self.source_id][i][2] = polygon.boundingRect()

    def mousePressEvent(self, event):
        pos = self.mapToScene(event.pos())
        # Добавление зоны
        if self.is_rect_clicked and event.button() == Qt.MouseButton.LeftButton:
            self.rectangle = self.scene.addRect(0, 0, 5, 5)
            self.rectangle.setPos(pos)
            self.rectangle.setPen(self.red_pen)
            self.rectangle.setBrush(self.red_brush)
        elif self.is_poly_clicked and event.button() == Qt.MouseButton.LeftButton:
            scene_point = self.mapToScene(event.pos())
            img_point = self.pix.mapFromScene(scene_point)

            self.polygon_coords.append((img_point.x() / self.pix.pixmap().width(),
                                        img_point.y() / self.pix.pixmap().height()))
            poly = self.polygon.polygon()
            poly.append(img_point)
            self.polygon.setPolygon(poly)
        elif self.is_poly_clicked and event.button() == Qt.MouseButton.RightButton:
            # Для завершения отрисовки полигона финальная точка ставится правой кнопкой мыши
            scene_point = self.mapToScene(event.pos())
            img_point = self.pix.mapFromScene(scene_point)

            self.polygon_coords.append((img_point.x() / self.pix.pixmap().width(),
                                        img_point.y() / self.pix.pixmap().height()))
            poly = self.polygon.polygon()
            poly.append(img_point)
            self.polygon.setPolygon(poly)
            self.sources_zones[self.source_id].append(['poly', self.polygon_coords, self.polygon.boundingRect()])
            if str(self.source_id) not in self.params['events_detectors']['ZoneEventsDetector']['sources']:
                self.params['events_detectors']['ZoneEventsDetector']['sources'][str(self.source_id)] = [self.polygon_coords]
            else:
                self.params['events_detectors']['ZoneEventsDetector']['sources'][str(self.source_id)].append(self.polygon_coords)
            # Оповещаем о добавлении зоны
            threading_events.notify('new zone', self.source_id, self.polygon_coords, 'poly')
            # Отправляем сигнал об изменении
            self.zone_added.emit()
            self.polygon_coords = []
            self.polygon = QGraphicsPolygonItem(self.pix)
            self.polygon.setPen(self.red_pen)
            self.polygon.setBrush(self.red_brush)
        # Удаление зоны
        if self.is_rect_clicked_del and event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            self.scene.removeItem(item)
            rect = item.boundingRect()
            top_left = QPointF(rect.x(), rect.y()).toPoint()
            rect_size = QPointF(rect.width(), rect.height()).toPoint()

            filtered_zones = []
            filtered_coords = []
            for zone_type, zone_coords, it in self.sources_zones[self.source_id]:
                if ZoneForm(zone_type) == ZoneForm.Polygon:
                    # Если полигон, сравниваем ограничивающие прямоугольники для каждого элемента сцены
                    top_left_it = QPointF(it.x(), it.y()).toPoint()
                    rect_size_it = QPointF(it.width(), it.height()).toPoint()
                    if not (top_left == top_left_it and rect_size == rect_size_it):
                        filtered_zones.append([zone_type, zone_coords, it])
                        filtered_coords.append(zone_coords)
                    else:
                        threading_events.notify('zone deleted', self.source_id, zone_coords)
                elif ZoneForm(zone_type) == ZoneForm.Rectangle:
                    # Для прямоугольника сравниваем его координаты
                    top_left = self.mapFromScene(item.mapToScene(item.boundingRect().x(), item.boundingRect().y()))
                    item_size = QPointF(item.boundingRect().width(), item.boundingRect().height()).toPoint()
                    zone_top_left = self.mapFromScene(
                        self.pix.mapToScene(zone_coords[0][0] * self.pix.pixmap().width(),
                                            zone_coords[0][1] * self.pix.pixmap().height()))
                    zone_size = self.pix.mapFromScene(self.pix.mapToScene((zone_coords[2][0] - zone_coords[0][0]) * self.pix.pixmap().width(),
                                                                          (zone_coords[2][1] - zone_coords[0][1]) * self.pix.pixmap().height())).toPoint()
                    if not (top_left.x() - 2 <= zone_top_left.x() <= top_left.x() + 2 and
                            top_left.y() - 2 <= zone_top_left.y() <= top_left.y() + 2 and
                            item_size.x() - 2 <= zone_size.x() <= item_size.x() + 2 and
                            item_size.y() - 2 <= zone_size.y() <= item_size.y() + 2):
                        filtered_zones.append((zone_type, zone_coords, it))
                        filtered_coords.append(zone_coords)
                    else:
                        threading_events.notify('zone deleted', self.source_id, zone_coords)
            self.sources_zones[self.source_id] = filtered_zones
            self.params['events_detectors']['ZoneEventsDetector']['sources'][str(self.source_id)] = filtered_coords
            # Отправляем сигнал об изменении
            self.zone_removed.emit()
        event.accept()

    def mouseReleaseEvent(self, event):
        # При отпускании кнопки завершается отрисовка прямоугольной зоны
        if self.is_rect_clicked and event.button() == Qt.MouseButton.LeftButton:
            self.rectangle.setPen(self.red_pen)
            self.rectangle.setBrush(self.red_brush)

            pos = self.mapToScene(event.pos())
            top_left = self.pix.mapFromScene(self.rectangle.pos()).toPoint()
            bottom_right = self.pix.mapFromScene(pos).toPoint()
            zone_height = abs(bottom_right.y() - top_left.y())
            bottom_left = QPoint(top_left.x(), top_left.y() + zone_height)
            top_right = QPoint(bottom_right.x(), bottom_right.y() - zone_height)

            if top_left.y() > bottom_right.y():
                bottom_left = top_left
                top_right = bottom_right
                top_left = QPoint(top_left.x(), top_left.y() - zone_height)
                bottom_right = QPoint(bottom_right.x(), bottom_right.y() + zone_height)

            norm_top_left = (top_left.x() / self.pix.pixmap().width(), top_left.y() / self.pix.pixmap().height())
            norm_bottom_right = (bottom_right.x() / self.pix.pixmap().width(),
                                 bottom_right.y() / self.pix.pixmap().height())
            norm_top_right = (top_right.x() / self.pix.pixmap().width(), top_right.y() / self.pix.pixmap().height())
            norm_bottom_left = (bottom_left.x() / self.pix.pixmap().width(),
                                bottom_left.y() / self.pix.pixmap().height())
            norm_zone_coords = [(norm_top_left[0], norm_top_left[1]), (norm_top_right[0], norm_top_right[1]),
                                (norm_bottom_right[0], norm_bottom_right[1]), (norm_bottom_left[0], norm_bottom_left[1])]
            if str(self.source_id) not in self.params['events_detectors']['ZoneEventsDetector']['sources']:
                self.params['events_detectors']['ZoneEventsDetector']['sources'][str(self.source_id)] = [norm_zone_coords]
            else:
                self.params['events_detectors']['ZoneEventsDetector']['sources'][str(self.source_id)].append(norm_zone_coords)
            self.sources_zones[self.source_id].append(['rect', norm_zone_coords, self.rectangle.boundingRect()])
            # Оповещаем о добавлении зоны
            threading_events.notify('new zone', self.source_id, norm_zone_coords, 'rect')
            # Отправляем сигнал об изменении
            self.zone_added.emit()
        self.rectangle = None
        self.is_rect_clicked = False
        event.accept()

    def mouseMoveEvent(self, event):
        # Для эффекта увеличения прямоугольника при движении мыши
        super().mouseMoveEvent(event)
        pos = self.mapToScene(event.pos())
        if self.rectangle and self.is_rect_clicked:
            point = pos - self.rectangle.pos()
            self.rectangle.setRect(0, 0, point.x(), point.y())
        event.accept()

    def get_zone_info(self):
        return self.sources_zones

    def rect_clicked(self, flag):
        self.is_rect_clicked = flag

    def polygon_clicked(self, flag):
        self.is_poly_clicked = flag

    def del_rect_clicked(self, flag):
        self.is_rect_clicked_del = flag

    def resizeEvent(self, event):
        """Автоматически подстраивать масштаб при изменении размера окна"""
        super().resizeEvent(event)
        if self.pix is not None:
            # Используем QTimer для отложенного вызова fitInView
            # Это решает проблему с неправильным размером view при resizeEvent
            QTimer.singleShot(0, self._delayed_fit_in_view)
    
    def _delayed_fit_in_view(self):
        """Отложенное масштабирование изображения на все доступное пространство"""
        if self.pix is not None:
            self.fitInView(self.pix, Qt.AspectRatioMode.KeepAspectRatio)
            self.centerOn(self.pix.pos())

    def closeEvent(self, event):
        super().closeEvent(event)
        self.pix = None
        self.rectangle = None
        self.is_rect_clicked = False
        self.is_rect_clicked_del = False
        self.scene.clear()


class ZoneWindow(QWidget):
    # Сигналы для уведомления о событиях
    zones_updated = pyqtSignal(list)  # zones
    zone_editor_closed = pyqtSignal(dict, int, bool)  # zones_data, source_id, accepted
    
    def __init__(self, params):
        super().__init__()
        self.logger = get_module_logger("zone_window")
        self.params = params
        self.zone_params = self.params['events_detectors'].get('ZoneEventsDetector', dict()).get('sources', list())
        self.vis_params = self.params['visualizer']
        sources_zones = {}
        for source_id in self.zone_params:  # Приводим зоны, заданные координатами в json, к необходимому виду
            sources_zones[int(source_id)] = []
            for zones_coords in self.zone_params[source_id]:
                sources_zones[int(source_id)].append(['poly', zones_coords, None])

        self.view = GraphicsView(self, sources_zones=sources_zones, params=self.params)
        self.pixmap = None

        self.is_rect_clicked = False
        
        # Добавляем флаги для отслеживания изменений
        self.current_source_id = None
        self.saved_zones_data = None
        self.has_unsaved_changes = False

        self.setWindowTitle('Zone Editor')

        self._create_actions()
        self._create_toolbar()

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.drawing_toolbar)
        self.layout.addWidget(self.view)
        self.setLayout(self.layout)

    def set_cv_image(self, source_id, cv_image):
        """
        Устанавливает OpenCV изображение для отображения в ZoneWindow.
        Принимает только OpenCV изображение (numpy array).
        """
        import cv2
        import numpy as np
        
        # Проверяем, что это OpenCV изображение
        if not isinstance(cv_image, np.ndarray):
            raise TypeError(f"Expected OpenCV image (numpy array), got {type(cv_image)}")
        
        height, width = cv_image.shape[:2]
        
        # Конвертируем BGR в RGB для Qt
        if len(cv_image.shape) == 3:
            rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
        else:
            rgb_image = cv_image
        
        # Создаем QPixmap из OpenCV изображения
        try:
            from PyQt6.QtGui import QImage
        except ImportError:
            from PyQt5.QtGui import QImage
        
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image)
        
        self.logger.info(f"Converted OpenCV image {width}x{height} to QPixmap for ZoneWindow")
        
        # Устанавливаем минимальный размер окна, но позволяем ему быть больше
        min_width = max(800, width + 50)  # Минимум 800px или размер изображения + отступы
        min_height = max(600, height + 100)  # Минимум 600px или размер изображения + отступы для тулбара
        self.resize(QSize(min_width, min_height))
        self.view.add_pixmap(source_id, pixmap)
        
        # Сохраняем текущий источник и исходное состояние зон
        self.current_source_id = source_id
        self._save_initial_zones_state()

    def set_src_id(self, src_id):
        self.view.set_source_id(src_id)

    def load_zones_from_config(self, params, source_id):
        """Загрузить зоны из конфигурации для указанного источника"""
        try:
            zone_params = params.get('events_detectors', {}).get('ZoneEventsDetector', {}).get('sources', {})
            if str(source_id) in zone_params:
                zones_data = zone_params[str(source_id)]
                self.logger.info(f"Loaded {len(zones_data)} zones for source {source_id}")
                return zones_data
            else:
                self.logger.info(f"No zones found for source {source_id}")
                return []
        except Exception as e:
            self.logger.error(f"Error loading zones from config: {e}")
            return []

    def get_zones_for_source(self, source_id):
        """Получить зоны для указанного источника из текущей конфигурации"""
        return self.load_zones_from_config(self.params, source_id)

    def close(self):
        self.logger.info('Events journal closed')

    def _create_actions(self):  # Добавление кнопок
        self.rect_zone = QAction('&Draw a rectangle', self)
        icon_path = os.path.join(utils.get_project_root(), 'icons', 'zone_rect.svg')
        self.rect_zone.setIcon(QIcon(icon_path))
        self.rect_zone.triggered.connect(self.draw_rect)
        self.polygon_zone = QAction('&Draw a polygon', self)
        icon_path = os.path.join(utils.get_project_root(), 'icons', 'zone_polygon.svg')
        self.polygon_zone.setIcon(QIcon(icon_path))
        self.polygon_zone.triggered.connect(self.draw_polygon)
        self.delete_zone = QAction('&Delete a zone', self)
        icon_path = os.path.join(utils.get_project_root(), 'icons', 'delete_zone.svg')
        self.delete_zone.setIcon(QIcon(icon_path))
        self.delete_zone.triggered.connect(self.remove_zone)

    def _create_toolbar(self):
        self.drawing_toolbar = QToolBar('Draw a zone', self)
        self.drawing_toolbar.addAction(self.rect_zone)
        self.drawing_toolbar.addAction(self.polygon_zone)
        self.drawing_toolbar.addAction(self.delete_zone)
        self.toolbar_width = self.drawing_toolbar.frameGeometry().width()
    

    def get_zone_info(self):
        return self.view.get_zone_info()

    @pyqtSlot()
    def draw_rect(self):
        self.view.rect_clicked(True)
        self.view.polygon_clicked(False)
        self.view.del_rect_clicked(False)
        # Подключаем обработчик для отслеживания изменений
        self.view.zone_added.connect(self._on_zone_changed)

    @pyqtSlot()
    def draw_polygon(self):
        self.view.polygon_clicked(True)
        self.view.rect_clicked(False)
        self.view.del_rect_clicked(False)
        # Подключаем обработчик для отслеживания изменений
        self.view.zone_added.connect(self._on_zone_changed)

    @pyqtSlot()
    def remove_zone(self):
        self.view.del_rect_clicked(True)
        self.view.rect_clicked(False)
        self.view.polygon_clicked(False)
        # Подключаем обработчик для отслеживания изменений
        self.view.zone_removed.connect(self._on_zone_changed)
    
    def _on_zone_changed(self):
        """Обработчик изменений зон"""
        self.has_unsaved_changes = True

    def closeEvent(self, event) -> None:
        # Проверяем, были ли изменения
        if self.has_unsaved_changes or self._check_zones_changes():
            try:
                if pyqt_version == 6:
                    from PyQt6.QtWidgets import QMessageBox as _QMB
                    StdBtn = _QMB.StandardButton
                    buttons = StdBtn.Yes | StdBtn.No | StdBtn.Cancel
                else:
                    from PyQt5.QtWidgets import QMessageBox as _QMB
                    StdBtn = _QMB
                    buttons = _QMB.Yes | _QMB.No | _QMB.Cancel
            except Exception:
                from PyQt5.QtWidgets import QMessageBox as _QMB
                StdBtn = _QMB
                buttons = _QMB.Yes | _QMB.No | _QMB.Cancel
            
            mb = _QMB()
            mb.setWindowTitle("Save changes?")
            mb.setText("Zones have changed. Save changes?")
            mb.setStandardButtons(buttons)
            res = mb.exec()
            yes = StdBtn.Yes
            no = StdBtn.No
            cancel = StdBtn.Cancel
            
            if res == yes:
                # Принимаем изменения
                if self.current_source_id is not None:
                    zones_data = self.get_zones_for_source(self.current_source_id)
                    zones_dict = {str(self.current_source_id): zones_data}
                    self.zone_editor_closed.emit(zones_dict, self.current_source_id, True)
                event.accept()
            elif res == no:
                # Отклоняем изменения
                if self.current_source_id is not None:
                    self._restore_initial_zones_state()
                    zones_data = self.get_zones_for_source(self.current_source_id)
                    zones_dict = {str(self.current_source_id): zones_data}
                    self.zone_editor_closed.emit(zones_dict, self.current_source_id, False)
                event.accept()
            else:
                # Отменяем закрытие
                event.ignore()
                return
        else:
            # Нет изменений, просто закрываем
            if self.current_source_id is not None:
                zones_data = self.get_zones_for_source(self.current_source_id)
                zones_dict = {str(self.current_source_id): zones_data}
                self.zone_editor_closed.emit(zones_dict, self.current_source_id, False)
            event.accept()
        
        super().closeEvent(event)
        self.view.close()

    def resizeEvent(self, event):
        """Обработка изменения размера окна"""
        super().resizeEvent(event)
        # Уведомляем GraphicsView об изменении размера
        if hasattr(self.view, 'resizeEvent'):
            self.view.resizeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self.view.setVisible(True)
    
    def _save_initial_zones_state(self):
        """Сохраняет исходное состояние зон для сравнения изменений"""
        if self.current_source_id is not None:
            zones_data = self.get_zones_for_source(self.current_source_id)
            self.saved_zones_data = zones_data.copy() if zones_data else []
            self.has_unsaved_changes = False
    
    
    def _check_zones_changes(self):
        """Проверяет, были ли изменены зоны по сравнению с исходным состоянием"""
        if self.current_source_id is None or self.saved_zones_data is None:
            return False
        
        current_zones = self.get_zones_for_source(self.current_source_id)
        current_zones = current_zones if current_zones else []
        
        # Сравниваем количество зон
        if len(current_zones) != len(self.saved_zones_data):
            return True
        
        # Сравниваем содержимое зон
        for i, (current_zone, saved_zone) in enumerate(zip(current_zones, self.saved_zones_data)):
            if current_zone != saved_zone:
                return True
        
        return False
    
    
    def _restore_initial_zones_state(self):
        """Восстанавливает исходное состояние зон"""
        if self.current_source_id is not None and self.saved_zones_data is not None:
            # Очищаем текущие зоны
            if str(self.current_source_id) in self.params['events_detectors']['ZoneEventsDetector']['sources']:
                del self.params['events_detectors']['ZoneEventsDetector']['sources'][str(self.current_source_id)]
            
            # Восстанавливаем исходные зоны
            if self.saved_zones_data:
                self.params['events_detectors']['ZoneEventsDetector']['sources'][str(self.current_source_id)] = self.saved_zones_data
            
            # Обновляем внутреннее состояние view
            if self.current_source_id in self.view.sources_zones:
                self.view.sources_zones[self.current_source_id] = []
                for zone_coords in self.saved_zones_data:
                    self.view.sources_zones[self.current_source_id].append(['poly', zone_coords, None])
            
            self.has_unsaved_changes = False
