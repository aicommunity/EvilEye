"""Opt-in real RF-DETR smoke through the plugin process runtime."""
import os
import time
from pathlib import Path

import numpy as np
import pytest

from evileye.core.base_class import EvilEyeBase
from evileye.core.frame import Frame
from evileye.core.frame_transport import SharedFrameTransport
from evileye.object_detector import register_builtin_modules

_MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "rf-detr-nano.pth"
_RUN_REAL_MODEL_SMOKE = os.environ.get("EVILEYE_RUN_MODEL_PROCESS_SMOKE") == "1"


@pytest.mark.skipif(
    not _RUN_REAL_MODEL_SMOKE or not _MODEL_PATH.is_file(),
    reason="set EVILEYE_RUN_MODEL_PROCESS_SMOKE=1 and provide models/rf-detr-nano.pth",
)
def test_rfdetr_detector_runs_real_model_in_spawn_worker():
    owner = SharedFrameTransport()
    handle = owner.alloc_frame(
        np.zeros((64, 64, 3), dtype=np.uint8), frame_id=17, timestamp=17.0
    )
    previous_cwd = Path.cwd()
    adapter = None
    try:
        # RF-DETR's public package resolves its named pretrained checkpoint
        # against the working directory; use the repository's local checkpoint
        # without copying it or triggering a download.
        os.chdir(_MODEL_PATH.parent)
        register_builtin_modules()
        adapter = EvilEyeBase.create_instance("ObjectDetectorRfdetr")
        adapter.set_params(
            module_id="ObjectDetectorRfdetr",
            execution_mode="process",
            source_ids=[0],
            worker_count=1,
            model="rfdetr-nano",
            classes=["person"],
            inference_size=384,
            conf=0.99,
            device="cuda",
            half=False,
        )
        assert adapter.init() is True
        adapter.start()

        frame = Frame()
        frame.source_id = 0
        frame.frame_id = 17
        frame.frame_handle = handle
        adapter.put(frame)

        deadline = time.monotonic() + 180
        output = None
        while time.monotonic() < deadline:
            output = adapter.get()
            if output is not None:
                break
            if adapter.degraded:
                raise AssertionError(f"RF-DETR process worker degraded: {adapter.get_runtime_stats()}")
            time.sleep(0.05)

        assert output is not None, adapter.get_debug_info({})
        result, returned_frame = output
        assert result.source_id == 0
        assert result.frame_id == 17
        assert returned_frame.frame_handle == handle
        assert owner.get_frame_view(handle)[0, 0, 0] == 0
        assert adapter.get_runtime_stats()["degraded"] is False
    finally:
        if adapter is not None:
            adapter.stop()
            adapter.release()
        owner.release_frame(handle)
        os.chdir(previous_cwd)
