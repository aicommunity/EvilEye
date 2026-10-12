from __future__ import annotations

import time

import numpy as np

from evileye.core.base_class import EvilEyeBase
from evileye.core.frame import Frame
from evileye.core.frame_transport import SharedFrameTransport
from evileye.core.plugins import ModuleSpec, PLUGIN_API_VERSION, PluginSpec, plugin_registry
import evileye.core.plugin_runtime as plugin_runtime


class _FrameDescriptorEcho:
    def process_item(self, item, state):
        metadata, frame = item
        assert frame.image is None
        handle = frame.frame_handle
        image = SharedFrameTransport().get_frame_view(handle)
        return {"metadata": metadata, "shape": tuple(image.shape), "sum": int(image.sum())}, frame


def _register_descriptor_echo():
    plugin_id = "test_frame_handle_runtime"
    if plugin_registry.get_module(f"{plugin_id}/echo") is None:
        plugin_registry.register_plugin(
            PluginSpec(
                plugin_id=plugin_id,
                api_version=PLUGIN_API_VERSION,
                modules=(
                    ModuleSpec(
                        module_id="echo",
                        kind="processor_item",
                        factory=_FrameDescriptorEcho,
                        execution_modes=("process",),
                        capabilities=("accepts_frame_handle",),
                    ),
                ),
            )
        )
    return f"{plugin_id}/echo"


def test_process_runtime_transports_frame_handle_and_restores_parent_frame(monkeypatch):
    adapter = EvilEyeBase.create_instance(_register_descriptor_echo())
    adapter.set_params(module_id="test_frame_handle_runtime/echo", execution_mode="process")
    assert adapter.init() is True
    serialized_inputs = []
    serialize = plugin_runtime._serialize_process_value

    def observe_serialization(value, module_id, label):
        result = serialize(value, module_id, label)
        if label == "input item":
            serialized_inputs.append(len(result))
        return result

    monkeypatch.setattr(plugin_runtime, "_serialize_process_value", observe_serialization)
    adapter.start()
    frame = Frame()
    frame.source_id = 4
    frame.frame_id = 19
    frame.time_stamp = 12.5
    frame.image = np.full((720, 1280, 3), 17, dtype=np.uint8)
    expected_image = frame.image
    try:
        adapter.put(({"job": "descriptor"}, frame))
        deadline = time.monotonic() + 20
        output = None
        while output is None and time.monotonic() < deadline:
            output = adapter.get()
            if output is None:
                time.sleep(0.01)

        assert output is not None
        metadata, output_frame = output
        assert metadata == {
            "metadata": {"job": "descriptor"},
            "shape": (720, 1280, 3),
            "sum": int(expected_image.sum()),
        }
        assert output_frame is frame
        assert output_frame.image is expected_image
        assert serialized_inputs and serialized_inputs[0] < expected_image.nbytes // 100
        assert adapter._frame_transport._segments == {}
    finally:
        adapter.stop()
        adapter.release()
