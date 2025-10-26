try:
    from PyQt6.QtCore import QThread, QMutex, pyqtSignal, QEventLoop, QTimer, pyqtSlot
    from PyQt6 import QtGui
    from PyQt6.QtCore import Qt, QPointF, QRectF
    from PyQt6.QtGui import QPixmap, QPainter, QPen, QBrush, QColor, QPolygonF
    pyqt_version = 6
except ImportError:
    from PyQt5.QtCore import QThread, QMutex, pyqtSignal, QEventLoop, QTimer, pyqtSlot
    from PyQt5 import QtGui
    from PyQt5.QtCore import Qt, QPointF, QRectF
    from PyQt5.QtGui import QPixmap, QPainter, QPen, QBrush, QColor, QPolygonF
    pyqt_version = 5

from timeit import default_timer as timer
from ..utils import utils
from queue import Queue
from queue import Empty
import copy
import time
import cv2
from ..events_detectors.zone import ZoneForm
import logging


class VideoThread(QThread):
    handler = None
    thread_counter = 0
    rows = 0
    cols = 0
    # Сигнал, отвечающий за обновление label, в котором отображается изображение из потока
    update_image_signal = pyqtSignal(int, QPixmap)
    # Сигнал с оригинальным OpenCV изображением для ROI Editor
    update_original_cv_image_signal = pyqtSignal(int, object)  # object = cv2 image
    # Сигнал с чистым OpenCV изображением без нарисованных элементов для ROI Editor
    clean_image_available_signal = pyqtSignal(int, object)  # object = clean cv2 image
    display_zones_signal = pyqtSignal(dict)
    add_zone_signal = pyqtSignal(int, QPixmap)
    add_roi_signal = pyqtSignal(int, QPixmap)

    def __init__(self, source_id, fps, rows, cols, show_debug_info, font_params, text_config=None, class_mapping=None, logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        super().__init__()
        base_name = "evileye.video_thread"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)

        VideoThread.rows = rows  # Количество строк и столбцов для правильного перевода изображения в полный экран
        VideoThread.cols = cols
        self.queue = Queue(maxsize=fps)

        self.thread_num = VideoThread.thread_counter
        self.source_id = source_id
        self.zones = None
        self.show_zones = False
        self.is_add_zone_clicked = False
        self.is_add_roi_clicked = False

        self.run_flag = False
        self.show_debug_info = show_debug_info
        self.fps = fps
        self.thread_num = VideoThread.thread_counter  # Номер потока для определения, какой label обновлять
        self.det_params = None
        self.text_config = text_config or {}  # Text configuration for rendering
        self.visualizer_ref = None
        self.class_mapping = class_mapping or {}  # Class mapping for displaying class names

        # Event signalization (visual alert) parameters
        self.signal_enabled = False
        self.signal_color = QColor(255, 0, 0)
        # active events per this source: name -> { 'bbox': [x1,y1,x2,y2] (normalized) }
        self.active_events: dict[str, dict] = {}
        # Persistent object boxes to bridge short tracker gaps: obj_id -> { 'box': [x1,y1,x2,y2] px, 'ttl': int }
        self.persist_obj_boxes: dict[int, dict] = {}
        self.signal_hold_frames = 10
        
        # Thread-safe storage for clean images (before any drawing)
        self.last_clean_image = None
        self.clean_image_mutex = QMutex()

        # Таймер для задания fps у видеороликов
        self.timer = QTimer()
        self.timer.moveToThread(self)
        self.timer.timeout.connect(self.process_image)
        self.display_zones_signal.connect(self.display_zones)

        self.widget_width = 1920
        self.widget_height = 1080

        if font_params:
            self.font_scale = font_params.get('scale', 3)
            self.font_thickness = font_params.get('thickness', 5)
            self.font_color = font_params.get('color', (0, 0, 255))
        else:
            self.font_scale = 3
            self.font_thickness = 5
            self.font_color = (0, 0, 255)

        # Определяем количество потоков в зависимости от параметра split
        VideoThread.thread_counter += 1

    def start_thread(self):
        self.run_flag = True
        self.start()

    def append_data(self, data):
        if self.queue.full():
            self.queue.get()
        self.queue.put(data)

    def run(self):
        while self.run_flag:
            elapsed_seconds = self.process_image()
            sleep_seconds = 1. / self.fps - elapsed_seconds
            if sleep_seconds > 0.0:
                time.sleep(sleep_seconds)
            else:
                time.sleep(0.01)

    def set_main_widget_size(self, width, height):
        self.widget_width = width
        self.widget_height = height

    def convert_cv_qt(self, cv_img, widget_width, widget_height) -> QPixmap:
        # Переводим из opencv image в QPixmap
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        convert_to_qt = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
        if self.is_add_zone_clicked:
            zones_window_image = convert_to_qt.scaled(int(widget_width), int(widget_height),
                                                      Qt.AspectRatioMode.KeepAspectRatio)
            self.is_add_zone_clicked = False
            self.add_zone_signal.emit(self.thread_num, QPixmap.fromImage(zones_window_image))
        
        if self.is_add_roi_clicked:
            roi_window_image = convert_to_qt.scaled(int(widget_width), int(widget_height),
                                                    Qt.AspectRatioMode.KeepAspectRatio)
            self.is_add_roi_clicked = False
            self.add_roi_signal.emit(self.thread_num, QPixmap.fromImage(roi_window_image))
        # Подгоняем под указанный размер, но сохраняем пропорции
        scaled_image = convert_to_qt.scaled(int(widget_width / VideoThread.cols),
                                            int(widget_height / VideoThread.rows), Qt.AspectRatioMode.KeepAspectRatio)
        return QPixmap.fromImage(scaled_image)
    

    def _draw_signal_overlay(self, image: QPixmap):
        if not self.signal_enabled:
            return
        # Determine active events for this source; if none, skip overlay entirely
        active_keys = set()
        try:
            if self.visualizer_ref and hasattr(self.visualizer_ref, 'get_active_events'):
                active_keys = self.visualizer_ref.get_active_events(self.source_id)
        except Exception:
            active_keys = set()
        if not active_keys:
            return
        painter = QPainter(image)
        try:
            # QPainter ожидает RGB, но текущий источник цвета фактически интерпретируется как BGR —
            # для一致ности с OpenCV поменяем местами каналы для QPainter
            qcolor = QColor(self.signal_color.blue(), self.signal_color.green(), self.signal_color.red())
            pen = QPen(qcolor)
            pen.setWidth(4)
            painter.setPen(pen)
            # Draw border around full pixmap
            painter.drawRect(0, 0, image.width()-1, image.height()-1)
            # Draw active events list (top-left)
            painter.setBrush(QBrush())
            # Background for list (semi-transparent) с адаптацией контрастности к цвету события
            # Вычисляем яркость (перцептивная) цвета события и выбираем чёрный/белый фон для лучшего контраста
            r, g, b = qcolor.red(), qcolor.green(), qcolor.blue()
            luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
            if luminance > 128:
                # Яркий цвет события → тёмный фон
                bg = QColor(0, 0, 0)
                bg.setAlpha(140)
            else:
                # Тёмный цвет события → светлый фон
                bg = QColor(255, 255, 255)
                bg.setAlpha(140)
            # Build text list from visualizer centralized state
            text_lines = []
            for (_, obj_id, evt_name) in active_keys:
                text_lines.append(f"AttributeEvent: {evt_name} [{obj_id}]")
            if text_lines:
                pad = 6
                line_h = 18
                box_w = max(120, max((painter.fontMetrics().horizontalAdvance(t) for t in text_lines), default=0) + 2*pad)
                box_h = pad*2 + line_h*len(text_lines)
                painter.fillRect(0, 0, box_w, box_h, bg)
                painter.setPen(QPen(qcolor))
                for i, t in enumerate(text_lines):
                    painter.drawText(pad, pad + (i+1)*line_h - 4, t)
            # bbox событий теперь рисуются в utils.draw_boxes_tracking вместе с объектными
        finally:
            if painter.isActive():
                painter.end()

    def draw_zones(self, image: QPixmap, zones: dict):
        # self.logger.debug(zones)
        if not zones:
            return

        if self.source_id not in zones or not zones[self.source_id]:
            return

        src_zones = zones[self.source_id]
        brush = QBrush(QColor(255, 0, 0, 128))
        pen = QPen(Qt.GlobalColor.red)
        painter = QPainter(image)
        painter.setPen(pen)
        painter.setBrush(brush)
        width, height = image.width(), image.height()
        for zone_type, zone_coords, _ in src_zones:
            coords = [QPointF(point[0] * width, point[1] * height) for point in zone_coords]
            if ZoneForm(zone_type) == ZoneForm.Rectangle:
                rect = QRectF(coords[0], coords[2])
                painter.drawRect(rect)
            elif ZoneForm(zone_type) == ZoneForm.Polygon:
                painter.drawPolygon(QPolygonF(coords))

    def process_image(self):
        try:
            frame, track_info, source_name, source_duration_secs, debug_info = self.queue.get()
            begin_it = timer()
            
            # Create a copy of the image for display to avoid modifying the original
            import copy
            display_frame = copy.deepcopy(frame)
            
            # Store clean image in thread-safe storage (before any drawing)
            self.clean_image_mutex.lock()
            self.last_clean_image = copy.deepcopy(frame.image)
            self.clean_image_mutex.unlock()
            # Remember original size to normalize pixel bboxes to display size correctly
            try:
                ih, iw = display_frame.image.shape[:2]
                self.last_frame_w = iw
                self.last_frame_h = ih
            except Exception:
                self.last_frame_w = None
                self.last_frame_h = None
            
            # Update persistent boxes TTL and merge with latest boxes
            try:
                # Decrease TTL
                for oid in list(self.persist_obj_boxes.keys()):
                    self.persist_obj_boxes[oid]['ttl'] -= 1
                    if self.persist_obj_boxes[oid]['ttl'] <= 0:
                        del self.persist_obj_boxes[oid]
                # Refresh with latest boxes
                if isinstance(track_info, list):
                    for obj in track_info:
                        oid = getattr(obj, 'object_id', None)
                        bbox = None
                        if hasattr(obj, 'track') and hasattr(obj.track, 'bounding_box'):
                            bbox = obj.track.bounding_box
                        elif hasattr(obj, 'bounding_box'):
                            bbox = obj.bounding_box
                        if oid is not None and bbox is not None and len(bbox) == 4:
                            self.persist_obj_boxes[oid] = {'box': bbox, 'ttl': self.signal_hold_frames}
            except Exception:
                pass

            # Соберём активные obj_id для этого источника, чтобы рисовать красный bbox поверх зелёного
            active_obj_ids = set()
            try:
                if self.visualizer_ref and hasattr(self.visualizer_ref, 'get_active_events'):
                    active_keys = self.visualizer_ref.get_active_events(self.source_id) or set()
                    for (_, oid, _evt) in active_keys:
                        if oid is not None:
                            active_obj_ids.add(oid)
            except Exception:
                active_obj_ids = set()

            utils.draw_boxes_tracking(display_frame, track_info, source_name, source_duration_secs,
                                      self.font_scale, self.font_thickness, self.font_color,
                                      text_config=self.text_config, class_mapping=self.class_mapping,
                                      event_active_obj_ids=active_obj_ids,
                                      event_color=(self.signal_color.red(), self.signal_color.green(), self.signal_color.blue()))
            if self.show_debug_info:
                utils.draw_debug_info(display_frame, debug_info)
            qt_image = self.convert_cv_qt(display_frame.image, self.widget_width, self.widget_height)
            
            if self.show_zones:
                self.draw_zones(qt_image, self.zones)
            # Draw event signalization overlay last
            self._draw_signal_overlay(qt_image)
            end_it = timer()
            elapsed_seconds = end_it - begin_it
            # Сигнал из потока для обновления label на новое изображение
            self.update_image_signal.emit(self.thread_num, qt_image)
            # Сигнал с оригинальным OpenCV изображением для ROI Editor (до любых отрисовок)
            self.update_original_cv_image_signal.emit(self.thread_num, frame.image)
            # Сигнал с чистым OpenCV изображением без нарисованных элементов для ROI Editor (до любых отрисовок)
            self.clean_image_available_signal.emit(self.thread_num, frame.image)
            return elapsed_seconds
        except Empty:
            return 0
        except ValueError:
            return 0
        except Exception as e:
            try:
                self.logger.error(f"VideoThread.process_image error (src={self.source_id}): {e}")
            except Exception:
                pass
            return 0

    def stop_thread(self):
        self.run_flag = False
        self.logger.info('Visualization stopped')

    @pyqtSlot(dict)
    def display_zones(self, zones):
        if zones:
            self.show_zones = True
            self.zones = zones
        else:
            self.show_zones = False

    @pyqtSlot(int)
    def add_zone_clicked(self, thread_id):
        if self.thread_num == thread_id:
            self.is_add_zone_clicked = True
    
    @pyqtSlot(int)
    def add_roi_clicked(self, thread_id):
        if self.thread_num == thread_id:
            self.is_add_roi_clicked = True

    @pyqtSlot(bool, tuple)
    def set_signal_params(self, enabled: bool, color_rgb: tuple[int, int, int] = (255, 0, 0)):
        self.signal_enabled = enabled
        try:
            r, g, b = color_rgb
            self.signal_color = QColor(int(r), int(g), int(b))
        except Exception:
            self.signal_color = QColor(255, 0, 0)

    @pyqtSlot(str, bool, list)
    def set_event_state(self, event_name: str, is_on: bool, bbox_norm: list[float] | None = None):
        """Turn ON/OFF event visualization for this source. bbox_norm is [x1,y1,x2,y2] in [0..1]."""
        if not isinstance(event_name, str) or not event_name:
            return
        if is_on:
            self.active_events[event_name] = {'bbox': bbox_norm if bbox_norm and len(bbox_norm) == 4 else None}
        else:
            if event_name in self.active_events:
                del self.active_events[event_name]
    
    def get_clean_image(self):
        """Получить чистое изображение (до любых отрисовок) thread-safe способом"""
        self.clean_image_mutex.lock()
        clean_image = copy.deepcopy(self.last_clean_image) if self.last_clean_image is not None else None
        self.clean_image_mutex.unlock()
        return clean_image
