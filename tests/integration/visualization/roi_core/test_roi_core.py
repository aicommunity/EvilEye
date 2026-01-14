import pytest

try:
    from PyQt6.QtWidgets import QApplication
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QApplication
    pyqt_version = 5

import numpy as np

from evileye.visualization_modules.roi_core import ROIGraphicsView


@pytest.fixture(scope="module")
def qapp():
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def test_add_and_get_rois(qapp):
    view = ROIGraphicsView()
    # Подготовим фиктивное изображение 100x100
    if pyqt_version == 6:
        from PyQt6.QtGui import QImage, QPixmap
    else:
        from PyQt5.QtGui import QImage, QPixmap
    img = QImage(100, 100, QImage.Format.Format_RGB32 if pyqt_version == 6 else QImage.Format_RGB32)
    img.fill(0xFFFFFFFF)
    pixmap = QPixmap.fromImage(img)
    assert view.add_pixmap(pixmap)

    # Координаты источника
    view.source_to_display_scale = {'scale_x': 1.0, 'scale_y': 1.0}
    view.add_roi([10, 10, 30, 30], (255, 0, 0))
    rois = view.get_rois()
    assert len(rois) == 1
    assert rois[0]['coords'] == [10, 10, 30, 30]


def test_resize_roi_updates_data(qapp):
    view = ROIGraphicsView()
    if pyqt_version == 6:
        from PyQt6.QtGui import QImage, QPixmap
    else:
        from PyQt5.QtGui import QImage, QPixmap
    img = QImage(200, 100, QImage.Format.Format_RGB32 if pyqt_version == 6 else QImage.Format_RGB32)
    img.fill(0xFFFFFFFF)
    pixmap = QPixmap.fromImage(img)
    assert view.add_pixmap(pixmap)
    view.source_to_display_scale = {'scale_x': 1.0, 'scale_y': 1.0}

    item = view.add_roi([20, 20, 60, 60], (255, 0, 0))
    assert item is not None
    view._select_roi(item)

    # Эмулируем обновление размера: двигаем нижний правый угол
    rect = item.rect()
    new_scene_pos = rect.bottomRight() + view.pixmap_item.pos()  # сцена
    view._update_roi_size(new_scene_pos, handle=None)
    rois = view.get_rois()
    assert len(rois) == 1
    # Должны остаться валидные координаты x1<x2, y1<y2
    x1, y1, x2, y2 = rois[0]['coords']
    assert x1 < x2 and y1 < y2
