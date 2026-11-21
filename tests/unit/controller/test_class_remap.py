"""The controller feeds detector class mappings into the global class space."""
import logging
from types import SimpleNamespace

from evileye.controller.controller import Controller
from evileye.core.class_manager import ClassManager


class _Stage:
    def __init__(self):
        self.calls = []

    def set_class_id_remap(self, detector, remap):
        self.calls.append((detector.module_id, dict(remap)))
        return True


def _controller(stage):
    controller = Controller.__new__(Controller)
    controller.class_manager = ClassManager()
    controller.logger = logging.getLogger("test.controller.remap")
    controller.pipeline = SimpleNamespace(processors=[stage])
    controller.visualizer = None
    controller.class_mapping = {}
    return controller


def test_second_detector_with_colliding_ids_gets_a_remap():
    stage = _Stage()
    controller = _controller(stage)

    assert controller._merge_detector_class_mapping(SimpleNamespace(module_id="yolo"), {"person": 0}) is True
    assert controller._merge_detector_class_mapping(SimpleNamespace(module_id="ppe"), {"helmet": 0}) is True

    assert stage.calls == [("yolo", {0: 0}), ("ppe", {0: 1})]
    assert controller.class_mapping == {"person": 0, "helmet": 1}


def test_unchanged_mapping_is_not_registered_twice():
    stage = _Stage()
    controller = _controller(stage)
    detector = SimpleNamespace(module_id="yolo")

    assert controller._merge_detector_class_mapping(detector, {"person": 0}) is True
    assert controller._merge_detector_class_mapping(detector, {"person": 0}) is False
    assert len(stage.calls) == 1
