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
    """Small importable plugin used to exercise the real source-to-tracker path."""

    def __init__(self, config=None):
        config = config or {}
        self.label = str(config["label"])
        self.delay_sec = float(config.get("delay_sec", 0.0))

    def process_item(self, item, state):
        from evileye.object_detector.object_detection_base import (
            DetectionResult,
            DetectionResultList,
        )

        if self.delay_sec:
            time.sleep(self.delay_sec)
        frame = item[-1] if isinstance(item, (list, tuple)) else item
        result = DetectionResultList()
        result.source_id = frame.source_id
        result.frame_id = frame.frame_id
        result.time_stamp = frame.time_stamp
        detection = DetectionResult()
        detection.bounding_box = [10, 10, 30, 30]
        detection.confidence = 0.95
        detection.class_id = 0
        detection.detection_data["plugin_label"] = self.label
        result.detections.append(detection)
        return result, frame


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


def _frame_key(item):
    frame = item[-1] if isinstance(item, (list, tuple)) else item
    source_id = getattr(frame, "source_id", None)
    frame_id = getattr(frame, "frame_id", None)
    if source_id is None or frame_id is None:
        return None
    return (
        int(source_id),
        int(getattr(frame, "connection_generation", 0) or 0),
        int(frame_id),
    )


def _detection_label(detection):
    if isinstance(detection, dict):
        details = detection.get("detection_data", {})
    else:
        details = getattr(detection, "detection_data", {})
    return details.get("plugin_label")


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
        trackers=[
            {
                "module_id": "ObjectTrackingBotsort",
                "execution_mode": "process",
                "source_ids": [17],
                "fps": 10,
                "queue_size": 64,
                "botsort_cfg": {"gmc_method": "none", "with_reid": False},
            }
        ],
    )

    source_frame_keys = set()
    detector_labels_by_frame = {}
    detector_result_count_by_frame = {}
    tracker_frame_keys = set()
    try:
        assert pipeline.init() is True
        pipeline.start()
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            result = pipeline.process()
            for item in result.get("sources", []) or []:
                key = _frame_key(item)
                if key is not None:
                    source_frame_keys.add(key)
            for item in result.get("detectors", []) or []:
                key = _frame_key(item)
                if key is None:
                    continue
                data = item[0] if isinstance(item, (list, tuple)) else {}
                detector_result_count_by_frame[key] = (
                    detector_result_count_by_frame.get(key, 0) + 1
                )
                labels = detector_labels_by_frame.setdefault(key, set())
                detections = (
                    data.get("detections", [])
                    if isinstance(data, dict)
                    else getattr(data, "detections", [])
                )
                labels.update(
                    label
                    for label in (
                        _detection_label(detection)
                        for detection in (detections or [])
                    )
                    if label is not None
                )
            for item in result.get("trackers", []) or []:
                key = _frame_key(item)
                if key is not None:
                    tracker_frame_keys.add(key)
            if (
                len(detector_labels_by_frame) >= frame_count
                and len(tracker_frame_keys) >= frame_count
                and pipeline.check_all_sources_finished()
                and not pipeline.get_pending_work_summary()
            ):
                break
            time.sleep(0.002)
    finally:
        pipeline.stop()
        pipeline.release()

    assert len(source_frame_keys) == frame_count
    assert set(detector_labels_by_frame) == source_frame_keys
    assert set(detector_result_count_by_frame) == source_frame_keys
    assert all(count == 1 for count in detector_result_count_by_frame.values())
    assert all(
        labels == {"fast", "slow"}
        for labels in detector_labels_by_frame.values()
    )
    assert tracker_frame_keys == source_frame_keys
    assert all(source_id == 17 for source_id, _, _ in source_frame_keys)
    assert pipeline.get_runtime_stats()["degraded"] is False
