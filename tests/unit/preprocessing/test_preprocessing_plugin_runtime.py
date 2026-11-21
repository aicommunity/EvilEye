from __future__ import annotations

import json
import time

import numpy as np
import pytest

from evileye.core.base_class import EvilEyeBase
from evileye.core.frame import Frame
from evileye.core.plugin_runtime import ItemModuleAdapter


@pytest.mark.parametrize("execution_mode", ["thread", "process"])
def test_builtin_preprocessor_runs_through_plugin_runtime(tmp_path, execution_mode):
    from evileye.preprocessing import PreprocessingPipeline
    from evileye.core.plugins import plugin_registry

    registered = plugin_registry.get_module("evileye/PreprocessingPipeline")
    assert registered is not None
    assert registered.spec.factory is PreprocessingPipeline
    assert registered.spec.kind == "processor_item"

    sequence_file = tmp_path / "empty_preprocessing.json"
    sequence_file.write_text(json.dumps({"preprocessing_sequence": []}), encoding="utf-8")

    processor = EvilEyeBase.create_instance("PreprocessingPipeline")
    assert isinstance(processor, ItemModuleAdapter)
    assert processor.accepts_frame_handle is True
    assert processor.requires_materialized_frame is False
    assert processor.emits_dto_type == "Frame"
    processor.set_params(
        module_id="evileye/PreprocessingPipeline",
        execution_mode=execution_mode,
        source_ids=[0],
        pipeline_file_name=str(sequence_file),
        queue_size=2,
    )
    assert processor.init() is True
    processor.start()

    frame = Frame()
    frame.source_id = 0
    frame.frame_id = 12
    frame.frame_version = 4
    frame.image = np.zeros((4, 4, 3), dtype=np.uint8)
    try:
        processor.put(frame)
        deadline = time.monotonic() + (15.0 if execution_mode == "process" else 3.0)
        result = None
        while result is None and time.monotonic() < deadline:
            result = processor.get()
            if result is None:
                time.sleep(0.02)

        assert result is not None
        assert result.source_id == 0
        assert result.frame_id == 12
        assert result.frame_version == 5
        assert result.image.shape == (4, 4, 3)
    finally:
        processor.stop()


def test_legacy_pipeline_config_selects_generic_preprocessor_adapter():
    from evileye.pipelines.pipeline_surveillance import PipelineSurveillance

    pipeline = PipelineSurveillance()
    pipeline._init_preprocessors(
        [{"type": "PreprocessingPipeline", "source_ids": [0], "execution_mode": "thread"}]
    )

    stage_processors = pipeline.processors[0].get_processors()
    assert len(stage_processors) == 1
    assert isinstance(stage_processors[0], ItemModuleAdapter)
    assert stage_processors[0].registered_module.qualified_id == "evileye/PreprocessingPipeline"
