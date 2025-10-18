try:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QLabel, QFormLayout,
        QGroupBox, QListWidget, QListWidgetItem, QPushButton, QCheckBox, QMessageBox
    )
    from PyQt6.QtGui import QIcon, QAction
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QAction, QLabel, QFormLayout,
        QGroupBox, QListWidget, QListWidgetItem, QPushButton, QCheckBox, QMessageBox
    )
    from PyQt5.QtGui import QIcon
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 5

import os
from typing import List

from ..core.logger import get_module_logger
from ..utils import utils as utils_utils

# Используем существующую реализацию холста и логики ROI из диалога
from .roi_core import ROIGraphicsView, ROICoordsDialog


class ROIEditorWindow(QWidget):
    """Немодальное окно для редактирования ROI (Region of Interest)."""

    roi_updated = pyqtSignal(list)  # Сигнал с обновленными ROI (список словарей {'coords': [x1,y1,x2,y2]})
    roi_editor_closed = pyqtSignal(list, int, int, bool)  # rois_xyxy, source_id, detector_index, accepted

    def __init__(self, params, parent=None):
        super().__init__(parent)
        self.logger = get_module_logger("roi_editor_window")
        self.params = params

        self.setWindowTitle("ROI Editor")
        self.resize(1200, 800)
        
        # Устанавливаем флаги для независимого окна
        self.setWindowFlags(Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self.current_source_id = None
        self.current_detector_index = None
        self.saved_rois_data = None
        self.has_unsaved_changes = False
        self._first_show_done = False

        self._create_actions()
        self._create_toolbar()
        self._setup_ui()

    # UI
    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.addWidget(self.drawing_toolbar)

        main_layout = QHBoxLayout()

        # Левая панель - холст
        self.roi_canvas = ROIGraphicsView()
        self.roi_canvas.roi_selected.connect(self._on_roi_selected)
        self.roi_canvas.roi_added.connect(self._on_roi_added)
        self.roi_canvas.roi_removed.connect(self._on_roi_removed)
        self.roi_canvas.roi_updated.connect(self._on_roi_updated)
        main_layout.addWidget(self.roi_canvas, 4)

        # Правая панель - управление
        right_panel = QVBoxLayout()

        #drawing_group = QGroupBox("Drawing Settings")
        #drawing_layout = QFormLayout(drawing_group)
        #right_panel.addWidget(drawing_group)

        roi_group = QGroupBox("ROI Controls")
        roi_layout = QVBoxLayout(roi_group)
        help_label = QLabel("Instructions:\n• Click and drag to create an ROI\n• Click an ROI to select it\n• Select an ROI in the list to edit it")
        help_label.setWordWrap(True)
        roi_layout.addWidget(help_label)

        self.roi_list = QListWidget()
        self.roi_list.setMaximumHeight(120)
        self.roi_list.itemSelectionChanged.connect(self._on_roi_selection_changed)
        roi_layout.addWidget(QLabel("ROI List:"))
        roi_layout.addWidget(self.roi_list)

        roi_buttons = QHBoxLayout()
        self.modify_roi_btn = QPushButton("Edit")
        self.modify_roi_btn.clicked.connect(self._modify_roi)
        self.modify_roi_btn.setEnabled(False)
        roi_buttons.addWidget(self.modify_roi_btn)

        self.delete_roi_btn = QPushButton("Delete")
        self.delete_roi_btn.clicked.connect(self._delete_roi_mode)
        self.delete_roi_btn.setEnabled(False)
        roi_buttons.addWidget(self.delete_roi_btn)
        roi_layout.addLayout(roi_buttons)

        right_panel.addWidget(roi_group)

        settings_group = QGroupBox("Settings")
        settings_layout = QFormLayout(settings_group)
        self.show_numbers_check = QCheckBox("Show numbers")
        self.show_numbers_check.setChecked(True)
        settings_layout.addRow("", self.show_numbers_check)
        right_panel.addWidget(settings_group)

        right_panel.addStretch()
        main_layout.addLayout(right_panel, 1)

        layout.addLayout(main_layout)
        self.setLayout(layout)

    def _create_actions(self):
        # Иконки (пытаемся найти в нескольких локациях)
        def _get_icon(name: str) -> QIcon:
            try:
                base_root = utils_utils.get_project_root()
            except Exception:
                base_root = os.path.dirname(__file__)
            candidates = [
                os.path.join(base_root, 'icons', name),
                os.path.join(os.path.dirname(base_root), 'icons', name),
                os.path.join(os.path.dirname(os.path.dirname(base_root)), 'icons', name),
            ]
            for p in candidates:
                if os.path.exists(p):
                    return QIcon(p)
            return QIcon()

        draw_icon = _get_icon('roi_draw.svg')
        delete_icon = _get_icon('roi_delete.svg')

        self.action_draw_roi = QAction('&Draw ROI', self)
        self.action_draw_roi.setIcon(draw_icon)
        self.action_draw_roi.triggered.connect(self._draw_roi_mode)

        self.action_delete_roi = QAction('&Delete ROI', self)
        self.action_delete_roi.setIcon(delete_icon)
        self.action_delete_roi.triggered.connect(self._delete_roi_mode)

        self.action_clear_all = QAction('&Clear All', self)
        self.action_clear_all.triggered.connect(self._clear_rois)

        self.action_show_all = QAction('&Show All', self)
        self.action_show_all.triggered.connect(self._show_all_rois)

    def _create_toolbar(self):
        self.drawing_toolbar = QToolBar('ROI Tools', self)
        self.drawing_toolbar.addAction(self.action_draw_roi)
        self.drawing_toolbar.addAction(self.action_delete_roi)
        self.drawing_toolbar.addSeparator()
        self.drawing_toolbar.addAction(self.action_clear_all)
        self.drawing_toolbar.addAction(self.action_show_all)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._first_show_done:
            try:
                self.showMaximized()
            except Exception:
                pass
            self._first_show_done = True

    # Public API
    def set_cv_image(self, source_id, cv_image):
        # Импорты зависят от версии PyQt
        import cv2
        if pyqt_version == 6:
            from PyQt6.QtGui import QImage, QPixmap
        else:
            from PyQt5.QtGui import QImage, QPixmap

        # Конвертация BGR->RGB и в QPixmap
        rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
        h, w = rgb_image.shape[:2]
        bytes_per_line = 3 * w
        qt_format = QImage.Format.Format_RGB888 if pyqt_version == 6 else QImage.Format_RGB888
        qimg = QImage(rgb_image.data, w, h, bytes_per_line, qt_format)
        pixmap = QPixmap.fromImage(qimg)

        # Установка изображения в холст
        self.roi_canvas.add_pixmap(pixmap)

        # Сохраняем текущий источник
        self.current_source_id = source_id
        # Устанавливаем коэффициенты преобразования источник→отображение (равны 1.0 при совпадении размеров)
        try:
            src_h, src_w = cv_image.shape[:2]
            disp_w, disp_h = pixmap.width(), pixmap.height()
            scale_x = disp_w / src_w if src_w else 1.0
            scale_y = disp_h / src_h if src_h else 1.0
            self.roi_canvas.source_to_display_scale = {
                'scale_x': scale_x,
                'scale_y': scale_y,
                'source_width': src_w,
                'source_height': src_h,
                'display_width': disp_w,
                'display_height': disp_h
            }
        except Exception:
            pass
        # Форсируем репейнт и подгонку
        try:
            self.roi_canvas.scene.update()
            self.roi_canvas.update()
            self.roi_canvas._delayed_fit_in_view()
        except Exception:
            pass

    def set_context(self, source_id: int, detector_index: int):
        self.current_source_id = source_id
        self.current_detector_index = detector_index
        # Новый контекст — сбрасываем флаги и снимок исходных ROI
        self.has_unsaved_changes = False
        self.saved_rois_data = None

    def set_rois_from_detector(self, rois_xywh: list):
        """Принять ROI из детектора (формат [x,y,w,h]) и установить в canvas (xyxy)."""
        try:
            self.logger.info(f"set_rois_from_detector called with {len(rois_xywh)} ROI")
            self.roi_canvas.clear_rois()
            converted = []
            for item in rois_xywh:
                if len(item) == 4:
                    x, y, w, h = [int(v) for v in item]
                    if w <= 0 or h <= 0:
                        continue
                    # xyxy с правой/нижней границей включительно
                    x2 = x + w - 1
                    y2 = y + h - 1
                    converted.append([x, y, x2, y2])
            # Установим напрямую в roi_data и отрисуем
            self.roi_canvas.roi_data = [{"coords": coords, "color": (255, 0, 0)} for coords in converted]
            self.logger.info(f"Set roi_data with {len(self.roi_canvas.roi_data)} entries")
            setattr(self.roi_canvas, '_loading_from_config', True)
            for i, entry in enumerate(self.roi_canvas.roi_data):
                self.logger.info(f"Adding ROI {i+1}/{len(self.roi_canvas.roi_data)}: {entry['coords']}")
                # Временно отключаем обновление сцены для каждого ROI
                roi_item = self.roi_canvas._create_roi_item(entry["coords"], entry.get("color", (255, 0, 0)))
                if roi_item:
                    self.roi_canvas.rois.append(roi_item)
                self.logger.info(f"ROI {i+1} added successfully")
            setattr(self.roi_canvas, '_loading_from_config', False)
            # Обновляем сцену один раз в конце
            self.roi_canvas.scene.update()
            self.logger.info("Finished adding ROI to canvas")
            # Обновляем список ROI и перерисовываем сцену
            self._update_roi_list()
            self.logger.info("Updated ROI list")
            # Принудительно обновляем canvas
            self.roi_canvas.scene.update()
            self.roi_canvas.update()
            self.roi_canvas.repaint()
            self.logger.info("Updated canvas scene")
            if self.roi_canvas.roi_data:
                self.roi_canvas.ensure_rois_visible()
                self.logger.info("Ensured ROI visibility")
            # Принудительно обновляем все окно
            self.update()
            self.repaint()
            # Сохраняем снимок исходного состояния для корректной проверки изменений
            try:
                self.saved_rois_data = [entry.get("coords", []) for entry in (self.roi_canvas.get_rois() or [])]
            except Exception:
                self.saved_rois_data = [entry.get("coords", []) for entry in self.roi_canvas.roi_data]
            self.has_unsaved_changes = False
        except Exception:
            pass

    def set_rois_from_config(self, params, source_id):
        """Совместимый слой: делегируем на диалоговую логику, но без диалога."""
        try:
            # Воспользуемся теми же методами, что и в диалоге
            # 1) Загрузим ROI
            rois_data = ROIEditorWindow._load_rois_static(params, source_id, self.roi_canvas)

            # 2) Очистим и применим
            self.roi_canvas.clear_rois()
            self.roi_canvas.roi_data = rois_data.copy()
            setattr(self.roi_canvas, '_loading_from_config', True)
            for roi_data in rois_data:
                coords = roi_data.get('coords', [])
                color = roi_data.get('color', (255, 0, 0))
                if len(coords) == 4:
                    self.roi_canvas.add_roi_direct(coords, color)
            setattr(self.roi_canvas, '_loading_from_config', False)
            self._update_roi_list()
            self.roi_canvas.scene.update()
            self.roi_canvas.update()
            if len(self.roi_canvas.roi_data) > 0:
                self.roi_canvas.ensure_rois_visible()
            # Сохраняем снимок исходного состояния для корректной проверки изменений
            try:
                self.saved_rois_data = [entry.get("coords", []) for entry in (self.roi_canvas.get_rois() or [])]
            except Exception:
                self.saved_rois_data = [entry.get("coords", []) for entry in self.roi_canvas.roi_data]
            self.has_unsaved_changes = False
        except Exception as e:
            self.logger.error(f"Error setting ROI from config: {e}")

    @staticmethod
    def _load_rois_static(params, source_id, roi_canvas):
        """Вынесенная часть из логики ROIEditorDialog.load_rois_from_config."""
        try:
            rois_data = []
            detectors = []
            if 'detectors' in params:
                detectors = params['detectors']
            elif 'pipeline' in params and isinstance(params['pipeline'], dict) and 'detectors' in params['pipeline']:
                detectors = params['pipeline']['detectors']
            elif 'pipeline' in params and isinstance(params['pipeline'], list):
                detectors = params['pipeline']
            else:
                return rois_data

            for detector in detectors:
                detector_source_ids = detector.get('source_ids', [])
                if source_id in detector_source_ids:
                    roi_list = detector.get('roi', [])
                    if roi_list and len(roi_list) > 0:
                        source_rois = roi_list[0] if roi_list else []
                        for roi_coords in source_rois:
                            if len(roi_coords) == 4:
                                x, y, width, height = roi_coords
                                x1, y1 = x, y
                                x2, y2 = x + width, y + height

                                if roi_canvas and roi_canvas.original_size:
                                    current_img_width, current_img_height = roi_canvas.original_size
                                    max_x = max(x1, x2)
                                    max_y = max(y1, y2)
                                    if max_x > current_img_width or max_y > current_img_height:
                                        original_img_width = max_x
                                        original_img_height = max_y
                                        scale_x = current_img_width / original_img_width
                                        scale_y = current_img_height / original_img_height
                                        if roi_canvas.source_to_display_scale is None:
                                            roi_canvas.source_to_display_scale = {
                                                'scale_x': scale_x,
                                                'scale_y': scale_y,
                                                'source_width': original_img_width,
                                                'source_height': original_img_height,
                                                'display_width': current_img_width,
                                                'display_height': current_img_height
                                            }
                                        rois_data.append({
                                            'coords': [x1, y1, x2, y2],
                                            'color': (255, 0, 0)
                                        })
                                    else:
                                        rois_data.append({
                                            'coords': [x1, y1, x2, y2],
                                            'color': (255, 0, 0)
                                        })
                                else:
                                    rois_data.append({'coords': [x1, y1, x2, y2], 'color': (255, 0, 0)})
            return rois_data
        except Exception:
            return []

    # Toolbar actions
    @pyqtSlot()
    def _draw_roi_mode(self):
        # В текущей реализации рисование включается нажатием ЛКМ на сцене,
        # поэтому просто показываем подсказку.
        QMessageBox.information(self, "Drawing Mode", "Click and drag over the image to create an ROI.")

    @pyqtSlot()
    def _delete_roi_mode(self):
        current_item = self.roi_list.currentItem()
        if current_item is None:
            QMessageBox.information(self, "Delete ROI", "Select an ROI in the list on the right.")
            return
        index = self.roi_list.row(current_item)
        self.roi_canvas.remove_roi(index)
        self._update_roi_list()
        self._emit_rois_updated()

    @pyqtSlot()
    def _clear_rois(self):
        self.roi_canvas.clear_rois()
        self._update_roi_list()
        self._emit_rois_updated()

    @pyqtSlot()
    def _show_all_rois(self):
        self.roi_canvas.ensure_rois_visible()

    # Handlers / helpers
    def _on_roi_selected(self, roi_data):
        try:
            index = self.roi_canvas.roi_data.index(roi_data)
            self.roi_list.setCurrentRow(index)
            self.modify_roi_btn.setEnabled(True)
            self.delete_roi_btn.setEnabled(True)
        except ValueError:
            pass

    def _on_roi_added(self, coords):
        # Игнорируем события, возникающие при загрузке из конфигурации
        if getattr(self.roi_canvas, '_loading_from_config', False):
            return
        self._update_roi_list()
        self._emit_rois_updated()
        self.has_unsaved_changes = True

    def _on_roi_removed(self, index):
        if getattr(self.roi_canvas, '_loading_from_config', False):
            return
        self._update_roi_list()
        self.modify_roi_btn.setEnabled(False)
        self.delete_roi_btn.setEnabled(False)
        self._emit_rois_updated()
        self.has_unsaved_changes = True

    def _on_roi_updated(self, index, coords):
        if getattr(self.roi_canvas, '_loading_from_config', False):
            return
        self._update_roi_list()
        self._emit_rois_updated()
        self.has_unsaved_changes = True

    def _on_roi_selection_changed(self):
        current_item = self.roi_list.currentItem()
        if current_item:
            self.modify_roi_btn.setEnabled(True)
            self.delete_roi_btn.setEnabled(True)
            current_index = self.roi_list.row(current_item)
            self.roi_canvas.select_roi_by_index(current_index)
        else:
            self.modify_roi_btn.setEnabled(False)
            self.delete_roi_btn.setEnabled(False)
            if self.roi_canvas.selected_roi:
                self.roi_canvas.selected_roi = None

    def _modify_roi(self):
        current_item = self.roi_list.currentItem()
        if not current_item:
            return
        current_index = self.roi_list.row(current_item)
        roi_data = self.roi_canvas.roi_data[current_index]
        coords = roi_data["coords"]
        try:
            dialog = ROICoordsDialog(self, coords)
            result = dialog.exec()
        except Exception as e:
            self.logger.error(f"Error opening ROICoordsDialog: {e}")
            return
        # Универсальная проверка результата диалога для PyQt5/6
        if hasattr(type(dialog), 'DialogCode'):
            accepted_code = type(dialog).DialogCode.Accepted
        elif hasattr(dialog, 'Accepted'):
            accepted_code = dialog.Accepted
        else:
            accepted_code = 1
        if result == accepted_code:
            new_coords = dialog.get_coords()
            if new_coords:
                self.roi_canvas.update_roi(current_index, new_coords)
                self._update_roi_list()
                self._emit_rois_updated()

    def _update_roi_list(self):
        self.roi_list.clear()
        for i, roi in enumerate(self.roi_canvas.roi_data):
            coords = roi.get('coords', [0, 0, 0, 0])
            item = QListWidgetItem(f"ROI_{i+1}: [{coords[0]}, {coords[1]}, {coords[2]}, {coords[3]}]")
            self.roi_list.addItem(item)

    def _emit_rois_updated(self):
        rois = self.roi_canvas.get_rois()
        self.roi_updated.emit(rois)

    # Совместимость: некоторые старые вызовы могли использовать _delete_roi
    def _delete_roi(self):
        self._delete_roi_mode()

    def closeEvent(self, event):
        # Определяем, были ли реальные изменения списка/координат ROI по сравнению с исходным снимком
        def _snapshot_current_rois():
            try:
                return [entry.get("coords", []) for entry in self.roi_canvas.get_rois()]
            except Exception:
                return []

        has_real_changes = self.has_unsaved_changes

        if has_real_changes:
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
            mb.setText("ROIs have changed. Save changes?")
            mb.setStandardButtons(buttons)
            res = mb.exec()
            yes = StdBtn.Yes
            no = StdBtn.No
            cancel = StdBtn.Cancel
            if res == yes:
                rois = self.roi_canvas.get_rois()
                rois_xyxy = [entry["coords"] for entry in rois]
                self.roi_editor_closed.emit(rois_xyxy, int(self.current_source_id or 0), int(self.current_detector_index or -1), True)
                event.accept()
            elif res == no:
                self.roi_editor_closed.emit([], int(self.current_source_id or 0), int(self.current_detector_index or -1), False)
                event.accept()
            else:
                event.ignore()
                return
        else:
            rois = self.roi_canvas.get_rois()
            rois_xyxy = [entry["coords"] for entry in rois]
            self.roi_editor_closed.emit(rois_xyxy, int(self.current_source_id or 0), int(self.current_detector_index or -1), False)
            event.accept()


