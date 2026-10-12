"""End-to-end coverage for external detector fanout in PipelineSurveillance."""

import time
import uuid
from pathlib import Path

import pytest

from evileye.core.plugins import (
    PLUGIN_API_VERSION,
    ModuleSpec,
    PluginSpec,
    plugin_registry,
)
from evileye.pipelines.pipeline_surveillance import PipelineSurveillance


class _TaggedDetector:
    """Small importable plugin used to exercise the real source-to-detector path."""

    def __init__(self, config=None):
        config = config or {}
        self.label = str(config["label"])
        self.delay_sec = float(config.get("delay_sec", 0.0))

    def process_item(self, item, state):
        if self.delay_sec:
            time.sleep(self.delay_sec)
        frame = item[-1] if isinstance(item, (list, tuple)) else item
        return [{"detections": [{"label": self.label}]}, frame]


def _make_finite_video(path: Path, frame_count: int) -> None:
    import cv2
    import numpy as np

    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (320, 240)
    )
    if not writer.isOpened():
        pytest.skip("OpenCV/FFmpeg cannot create an MP4 test input")
    try:
        for index in range(frame_count):
            image = np.zeros((240, 320, 3), dtype=np.uint8)
            cv2.putText(
                image,
                f"frame {index}",
                (10, 120),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
            writer.write(image)
    finally:
        writer.release()


@pytest.mark.parametrize("execution_mode", ["thread", "process"])
def test_surveillance_pipeline_merges_external_detectors_for_each_video_frame(
    tmp_path, execution_mode
):
    pytest.importorskip("cv2")
    frame_count = 16
    video_path = tmp_path / "plugin-fanout.mp4"
    _make_finite_video(video_path, frame_count)

    plugin_id = f"test.surveillance-e2e-{uuid.uuid4().hex}"
    plugin_registry.register_plugin(
        PluginSpec(
            plugin_id=plugin_id,
            api_version=PLUGIN_API_VERSION,
            modules=(
                ModuleSpec(
                    module_id="tagged_detector",
                    kind="processor_item",
                    factory=_TaggedDetector,
                    execution_modes=("thread", "process"),
                    default_execution_mode="thread",
                ),
            ),
        )
    )
    module_id = f"{plugin_id}/tagged_detector"
    pipeline = PipelineSurveillance()
    pipeline.set_params(
        pipeline_class="PipelineSurveillance",
        sources=[
            {
                "module_id": "VideoCaptureOpencv",
                "execution_mode": "thread",
                "source": "VideoFile",
                "camera": str(video_path),
                "source_ids": [17],
                "source_names": ["PluginFanout"],
                "desired_fps": 10,
                "loop_play": False,
                "queue_size": 64,
                "capture": {"queue_size": 64},
            }
        ],
        detectors=[
            {
                "module_id": module_id,
                "execution_mode": execution_mode,
                "source_ids": [17],
                "label": "fast",
                "queue_size": 64,
            },
            {
                "module_id": module_id,
                "execution_mode": execution_mode,
                "source_ids": [17],
                "label": "slow",
                "delay_sec": 0.06,
                "queue_size": 64,
            },
        ],
        trackers=[],
    )

    labels_by_frame = {}
    try:
        assert pipeline.init() is True
        pipeline.start()
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            result = pipeline.process()
            for data, frame in result.get("detectors", []) or []:
                labels_by_frame[int(frame.frame_id)] = {
                    detection["label"]
                    for detection in data.get("detections", [])
                }
            if (
                len(labels_by_frame) >= frame_count
                and pipeline.check_all_sources_finished()
                and not pipeline.get_pending_work_summary()
            ):
                break
            time.sleep(0.002)
    finally:
        pipeline.stop()
        pipeline.release()

    assert len(labels_by_frame) == frame_count
    assert all(labels == {"fast", "slow"} for labels in labels_by_frame.values())
    assert pipeline.get_runtime_stats()["degraded"] is False
