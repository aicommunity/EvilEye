try:
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QTabWidget, QPushButton, QGraphicsPixmapItem, QGraphicsTransform,
        QSizePolicy, QMenuBar, QToolBar, QDateTimeEdit, QHeaderView, QGraphicsView, QGraphicsScene,
        QMenu, QMainWindow, QMessageBox, QTableView, QTableWidget, QTableWidgetItem, QGraphicsRectItem,
        QGraphicsPolygonItem
    )
    from PyQt6.QtGui import QPixmap, QIcon, QAction, QPainter, QBrush, QPen, QColor, QPolygonF
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt, QPointF, QPoint, QSize, QRectF, QSizeF
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt, QPointF, QPoint, QSize, QRectF, QSizeF


    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QTabWidget, QPushButton, QGraphicsPixmapItem, QGraphicsTransform,
        QSizePolicy, QMenuBar, QToolBar, QDateTimeEdit, QHeaderView, QGraphicsView, QGraphicsScene,
        QMenu, QMainWindow, QMessageBox, QTableView, QTableWidget, QTableWidgetItem, QGraphicsRectItem,
        QGraphicsPolygonItem
    )
    from PyQt5.QtGui import QPixmap, QIcon, QPainter, QBrush, QPen, QColor, QPolygonF
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt, QPointF, QPoint, QSize, QRectF, QSizeF
    from PyQt5.QtWidgets import QAction
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt, QPointF, QPoint, QSize, QRectF, QSizeF

    pyqt_version = 5

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

    def closeEvent(self, event):
        super().closeEvent(event)
        self.pix = None
        self.rectangle = None
        self.is_rect_clicked = False
        self.is_rect_clicked_del = False
        self.scene.clear()


class ZoneWindow(QWidget):
    def __init__(self, params):
        super().__init__()
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

        self.setWindowTitle('Add Zone')

        self._create_actions()
        self._create_toolbar()

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.drawing_toolbar)
        self.layout.addWidget(self.view)
        self.setLayout(self.layout)

    def set_pixmap(self, source_id, pixmap):
        self.resize(QSize(pixmap.width() + 10, pixmap.height() + 10))
        self.view.add_pixmap(source_id, pixmap)

    def set_src_id(self, src_id):
        self.view.set_source_id(src_id)

    def close(self):
        print('Events journal closed')

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

    @pyqtSlot()
    def draw_polygon(self):
        self.view.polygon_clicked(True)
        self.view.rect_clicked(False)
        self.view.del_rect_clicked(False)

    @pyqtSlot()
    def remove_zone(self):
        self.view.del_rect_clicked(True)
        self.view.rect_clicked(False)
        self.view.polygon_clicked(False)

    def closeEvent(self, event) -> None:
        super().closeEvent(event)
        self.view.close()

    def showEvent(self, event):
        super().showEvent(event)
        self.view.setVisible(True)
