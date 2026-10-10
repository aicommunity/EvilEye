"""Per-item processor type + event registry smoke tests."""

from __future__ import annotations

import pytest

from evileye.core.base_class import EvilEyeBase
from evileye.core.processor_step import ProcessorStep
from evileye.events_detectors.event_registry import (
    list_event_detectors,
    register_builtins,
    register_event_detector,
)
from evileye.core.plugins import plugin_registry


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



def test_legacy_decorator_registers_in_plugin_registry_only():
    assert not hasattr(EvilEyeBase, "_registry")
    registered = plugin_registry.get_module("_AuditDummyA")
    assert registered is not None
    assert registered.spec.factory is _AuditDummyA
    assert isinstance(EvilEyeBase.create_instance("_AuditDummyA"), _AuditDummyA)

    with pytest.raises(ValueError, match="not found in plugin registry"):
        EvilEyeBase.create_instance("missing.audit/module")

def test_event_registry_builtins_and_custom():
    register_builtins()
    assert "ZoneEventsDetector" in list_event_detectors()

    @register_event_detector("_AuditHeartbeat")
    class _AuditHeartbeat:
        def __init__(self, *args, **kwargs):
            pass

    assert "_AuditHeartbeat" in list_event_detectors()


def test_builtin_event_detectors_register_when_custom_detector_was_loaded_first():
    class _LoadedFirst:
        pass

    plugin_registry.register_builtin_module(
        "_LoadedFirst", _LoadedFirst, kind="event_detector", execution_modes=("thread",)
    )

    register_builtins()

    assert "_LoadedFirst" in list_event_detectors()
    assert "ZoneEventsDetector" in list_event_detectors()
