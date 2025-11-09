import pytest

try:
    from PyQt6.QtWidgets import QApplication
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QApplication
    pyqt_version = 5

import numpy as np

from evileye.visualization_modules.roi_editor_window import ROIEditorWindow


@pytest.fixture(scope="module")
def qapp():
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def _fake_params_with_detector(source_id=0, roi_list=None):
    if roi_list is None:
        roi_list = [[10, 10, 20, 20]]  # [x, y, w, h]
    return {
        'detectors': [
            {
                'type': 'SomeDetector',
                'source_ids': [source_id],
                'roi': [roi_list]
            }
        ]
    }


def test_window_set_image_and_load_rois(qapp):
    params = _fake_params_with_detector(source_id=1, roi_list=[[5, 5, 10, 10]])
    win = ROIEditorWindow(params)

    # Создаём простое CV изображение 100x100 (BGR)
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[:, :] = (0, 0, 255)

    # Устанавливаем изображение и ROI
    win.set_cv_image(1, img)
    win.set_rois_from_config(params, 1)

    rois = win.roi_canvas.get_rois()
    assert isinstance(rois, list)
    assert len(rois) >= 1
    coords = rois[0]['coords']
    assert len(coords) == 4
    assert coords[0] < coords[2] and coords[1] < coords[3]
