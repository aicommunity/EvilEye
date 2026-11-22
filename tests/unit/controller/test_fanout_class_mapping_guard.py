"""Backlog fixes: TD-PS-D1 fanout class-mapping guard."""

from __future__ import annotations

import logging

import pytest


class _Detector:
    def __init__(self, module_id, mapping):
        self.module_id = module_id
        self._mapping = mapping

    def get_model_class_mapping(self):
        return self._mapping


def _controller_with(detectors):
    from evileye.controller.controller import Controller

    controller = Controller.__new__(Controller)
    controller.pipeline = object()
    controller.logger = logging.getLogger("test-fanout-guard")
    controller._get_pipeline_detectors = lambda: detectors
    # Minimal collaborators for the success path.
    controller._detector_class_mapping_cache = {}
    controller._merge_detector_class_mapping = lambda detector, mapping: True
    controller._apply_detector_class_remap = lambda detector, remap: None

    class _ClassManager:
        class_mapping = {}
        conflicts = []

        def get_conflicts(self):
            return []

        def get_class_mapping(self):
            return {}

    controller.class_manager = _ClassManager()
    return controller


def test_single_detector_without_mapping_is_allowed():
    controller = _controller_with([_Detector("det-a", None)])
    # No exception: a single detector defines the global class space itself.
    controller.update_class_mapping_from_detectors()


def test_fanout_with_all_mappings_is_allowed():
    controller = _controller_with(
        [
            _Detector("det-a", {"person": 0}),
            _Detector("det-b", {"hardhat": 0}),
        ]
    )
    controller.update_class_mapping_from_detectors()


def test_fanout_without_mapping_fails_start():
    controller = _controller_with(
        [
            _Detector("det-a", {"person": 0}),
            _Detector("det-b", None),
        ]
    )
    with pytest.raises(RuntimeError, match="det-b"):
        controller.update_class_mapping_from_detectors()
