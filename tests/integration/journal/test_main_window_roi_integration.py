import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    from PyQt5.QtWidgets import QApplication

from types import SimpleNamespace

from evileye.visualization_modules.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    return app


class DummyLogger:
    def info(self, *args, **kwargs):
        pass
    def error(self, *args, **kwargs):
        pass
    def warning(self, *args, **kwargs):
        pass


class MockDetector:
    def __init__(self, source_ids):
        self.source_ids = source_ids
        self.last_set = None
        self._rois_xywh = [[5, 5, 10, 10]]

    def get_source_ids(self):
        return self.source_ids if isinstance(self.source_ids, list) else [self.source_ids]

    def get_rois_for_source(self, source_id):
        return self._rois_xywh

    def set_rois_for_source(self, source_id, rois_xyxy):
        self.last_set = (source_id, rois_xyxy)


class MockPipeline:
    def __init__(self, detectors):
        self.detectors = detectors

    def get_detector_by_index(self, idx):
        return self.detectors[idx]

    # Совместимость с возможным API
    def get_detectors(self):
        return self.detectors


def make_minimal_main_window(qapp):
    # Создаём объект без вызова __init__, подменяем нужные атрибуты
    mw = MainWindow.__new__(MainWindow)
    mw.controller = SimpleNamespace(pipeline=None)
    mw.params = {}
    mw.logger = DummyLogger()
    # Add _roi_editor_detector attribute that might be used
    mw._roi_editor_detector = None
    return mw


def test_apply_roi_to_detector_by_index(qapp):
    det = MockDetector([1])
    pipeline = MockPipeline([det])
    mw = make_minimal_main_window(qapp)
    mw.controller.pipeline = pipeline

    rois_xyxy = [[0, 0, 20, 20], [10, 10, 30, 30]]
    mw._on_roi_editor_closed(rois_xyxy, source_id=1, detector_index=0, accepted=True)

    assert det.last_set is not None
    src, rois = det.last_set
    assert src == 1
    assert rois == rois_xyxy


def test_apply_roi_to_detector_by_source_match(qapp):
    # индекс неправильный, но по source_ids найдём подходящий
    det = MockDetector([2])
    pipeline = MockPipeline([det])
    mw = make_minimal_main_window(qapp)
    mw.controller.pipeline = pipeline

    rois_xyxy = [[1, 2, 3, 4]]
    # Передаем -1 для невалидного индекса, чтобы метод искал по source_id
    # Метод проверяет detector_index >= 0, поэтому -1 не пройдет проверку и метод будет искать по source_id
    mw._on_roi_editor_closed(rois_xyxy, source_id=2, detector_index=-1, accepted=True)

    assert det.last_set is not None
    src, rois = det.last_set
    assert src == 2
    assert rois == rois_xyxy


def test_get_rois_from_detector_pipeline_first(qapp):
    det = MockDetector([3])
    pipeline = MockPipeline([det])
    mw = make_minimal_main_window(qapp)
    mw.controller.pipeline = pipeline

    rois = mw._get_rois_from_detector(0, 3)
    assert isinstance(rois, list) and len(rois) == 1
    assert rois[0] == [5, 5, 10, 10]


def test_get_rois_from_params_fallback(qapp):
    # Без pipeline, читаем из params, где roi распределены по source_ids
    mw = make_minimal_main_window(qapp)
    mw.controller.pipeline = None
    mw.params = {
        'detectors': [
            {
                'source_ids': [7, 8],
                'roi': [
                    [[1, 1, 2, 2]],
                    [[3, 3, 4, 4]]
                ]
            }
        ]
    }
    rois = mw._get_rois_from_detector(0, 8)
    assert rois == [[3, 3, 4, 4]]
