"""Opt-in finite-video coverage for the migrated surveillance pipeline."""

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("EVILEYE_RUN_SURVEILLANCE_VIDEO_E2E") != "1",
    reason="set EVILEYE_RUN_SURVEILLANCE_VIDEO_E2E=1 to run the model-backed video E2E",
)


def _make_finite_video(path: Path, frame_count: int = 20) -> None:
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
            cv2.putText(image, f"frame {index}", (10, 120), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (0, 255, 0), 2, cv2.LINE_AA)
            cv2.rectangle(image, (10 + index * 5, 30), (30 + index * 5, 50),
                          (255, 0, 0), -1)
            writer.write(image)
    finally:
        writer.release()


def _frame_keys(items):
    for item in items or []:
        frame = item[-1] if isinstance(item, (list, tuple)) else item
        source_id = getattr(frame, "source_id", None)
        frame_id = getattr(frame, "frame_id", None)
        if source_id is not None and frame_id is not None:
            yield int(source_id), int(frame_id)


@pytest.mark.parametrize("execution_mode", ["thread", "process"])
def test_surveillance_pipeline_drains_finite_video_and_closes_workers(tmp_path, execution_mode):
    pytest.importorskip("cv2")
    from evileye.pipelines.pipeline_surveillance import PipelineSurveillance

    repo_root = Path(__file__).resolve().parents[3]
    model_path = repo_root / "models" / "yolo11n.pt"
    if not model_path.is_file():
        pytest.skip(f"model-backed E2E requires {model_path}")
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        pytest.skip("ffprobe is required to inspect the recorded segment")
    expected_frame_count = 20
    video_path = tmp_path / "finite-input.mp4"
    _make_finite_video(video_path, expected_frame_count)
    record_dir = tmp_path / "recordings"

    pipeline = PipelineSurveillance()
    pipeline.set_params(
        pipeline_class="PipelineSurveillance",
        sources=[{
            "module_id": "VideoCaptureOpencv",
            "execution_mode": "thread",
            "source": "VideoFile",
            "camera": str(video_path),
            "source_ids": [0],
            "source_names": ["FiniteE2E"],
            "desired_fps": 10,
            "loop_play": False,
            "queue_size": 64,
            "capture": {"queue_size": 64},
            "record": {
                "enabled": True,
                "continuous_recording_enabled": True,
                "container": "mp4",
                "segment_length_sec": 300,
                "retention_days": 3,
                "min_free_space_pct": 0,
                "min_file_size_kb": 0,
                "out_dir": str(record_dir),
                "filename_tmpl": "{source_name}_{start_time}_{seq}.{ext}",
            },
        }],
        detectors=[{
            "module_id": "ObjectDetectorYolo",
            "execution_mode": execution_mode,
            "model": str(model_path),
            "classes": [0],
            "source_ids": [0],
            "roi": [[]],
            "vid_stride": 1,
            "imgsz": 320,
            "conf": 0.5,
            "queue_size": 64,
        }],
        trackers=[{
            "module_id": "ObjectTrackingBotsort",
            "execution_mode": execution_mode,
            "source_ids": [0],
            "fps": 10,
            "queue_size": 64,
            "botsort_cfg": {"gmc_method": "none", "with_reid": False},
        }],
    )

    seen = {stage: set() for stage in ("sources", "detectors", "trackers")}
    try:
        assert pipeline.init() is True
        pipeline.start()
        deadline = time.monotonic() + 120.0
        while time.monotonic() < deadline:
            result = pipeline.process()
            for stage in seen:
                seen[stage].update(_frame_keys(result.get(stage, [])))
            if all(len(seen[stage]) >= expected_frame_count for stage in seen):
                break
            time.sleep(0.005)

        assert len(seen["sources"]) == expected_frame_count
        assert len(seen["detectors"]) == expected_frame_count
        assert len(seen["trackers"]) == expected_frame_count
        assert seen["detectors"] == seen["sources"]
        assert seen["trackers"] == seen["detectors"]
        assert all(source_id == 0 for source_id, _ in seen["sources"])
        assert pipeline.check_all_sources_finished()
        assert pipeline.get_runtime_stats()["degraded"] is False
    finally:
        pipeline.stop()
        pipeline.release()

    segments = list((record_dir / "Streams").rglob("*.mp4"))
    assert segments, f"capture recording did not produce an MP4 under {record_dir}"
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-count_packets",
         "-show_entries", "stream=nb_read_packets",
         "-of", "default=noprint_wrappers=1:nokey=1", str(segments[0])],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert int(probe.stdout.strip()) > 0

    runtime = pipeline.get_runtime_stats()
    assert runtime["degraded"] is False
    assert all(not module.get("worker_running", False)
               for module in runtime["modules"].values())
