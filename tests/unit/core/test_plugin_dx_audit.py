"""Per-item processor type + event registry smoke tests."""

from __future__ import annotations

from unittest.mock import patch

from evileye.core.base_class import EvilEyeBase
from evileye.core.processor_step import ProcessorStep
from evileye.events_detectors.event_registry import (
    list_event_detectors,
    register_builtins,
    register_event_detector,
)


@EvilEyeBase.register("_AuditDummyA")
class _AuditDummyA(EvilEyeBase):
    def init_impl(self, **kwargs):
        return True

    def set_params_impl(self):
        pass

    def get_params_impl(self):
        return {}

    def default(self):
        pass

    def release_impl(self):
        pass

    def reset_impl(self):
        pass

    def get_source_ids(self):
        return [0]


@EvilEyeBase.register("_AuditDummyB")
class _AuditDummyB(EvilEyeBase):
    def init_impl(self, **kwargs):
        return True

    def set_params_impl(self):
        pass

    def get_params_impl(self):
        return {}

    def default(self):
        pass

    def release_impl(self):
        pass

    def reset_impl(self):
        pass

    def get_source_ids(self):
        return [1]


def test_processor_step_per_item_types():
    step = ProcessorStep(
        processor_name="detectors",
        class_name="_AuditDummyA",
        num_processors=2,
        order=0,
        class_names=["_AuditDummyA", "_AuditDummyB"],
    )
    assert isinstance(step.processors[0], _AuditDummyA)
    assert isinstance(step.processors[1], _AuditDummyB)


def test_event_registry_builtins_and_custom():
    register_builtins()
    assert "ZoneEventsDetector" in list_event_detectors()

    @register_event_detector("_AuditHeartbeat")
    class _AuditHeartbeat:
        def __init__(self, *args, **kwargs):
            pass

    assert "_AuditHeartbeat" in list_event_detectors()
