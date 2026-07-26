from argparse import Namespace
import json
from pathlib import Path

from scripts.prepare_multiprocessing_benchmark import prepare_configs


def test_prepare_configs_can_build_shared_detector_pool(tmp_path: Path):
    args = Namespace(
        base_config="configs/multi_videos.json",
        out_dir=str(tmp_path),
        max_cameras=4,
        allow_missing=False,
        enable_server=False,
        repeat_cameras=True,
        num_detection_threads=1,
        shared_detector_pool=True,
        detector_process_only=False,
        capture_process_also=False,
        target_fps=30,
    )

    manifest = prepare_configs(args)
    process_config = json.loads((tmp_path / "bench_04cam_process.json").read_text(encoding="utf-8"))
    thread_config = json.loads((tmp_path / "bench_04cam_thread.json").read_text(encoding="utf-8"))

    assert manifest["shared_detector_pool"] is True

    process_detectors = process_config["pipeline"]["detectors"]
    assert len(process_detectors) == 1
    assert process_detectors[0]["source_ids"] == [0, 1, 2, 3]
    assert process_detectors[0]["roi"] == [[], [], [], []]
    assert process_detectors[0]["num_detection_threads"] == 1
    assert process_detectors[0]["execution_mode"] == "process"

    thread_detectors = thread_config["pipeline"]["detectors"]
    assert len(thread_detectors) == 1
    assert thread_detectors[0]["source_ids"] == [0, 1, 2, 3]
    assert thread_detectors[0]["execution_mode"] == "thread"
    assert process_config["controller"]["fps"] == 30.0
    assert all(
        source["desired_fps"] == 30.0
        for source in process_config["pipeline"]["sources"]
    )


def test_prepare_configs_can_process_only_detectors(tmp_path: Path):
    args = Namespace(
        base_config="configs/multi_videos.json",
        out_dir=str(tmp_path),
        max_cameras=4,
        allow_missing=False,
        enable_server=False,
        repeat_cameras=True,
        num_detection_threads=1,
        shared_detector_pool=False,
        detector_process_only=True,
        capture_process_also=False,
        target_fps=30,
    )

    manifest = prepare_configs(args)
    process_config = json.loads((tmp_path / "bench_04cam_process.json").read_text(encoding="utf-8"))
    thread_config = json.loads((tmp_path / "bench_04cam_thread.json").read_text(encoding="utf-8"))

    assert manifest["detector_process_only"] is True
    assert {
        source["execution_mode"]
        for source in process_config["pipeline"]["sources"]
    } == {"thread"}
    assert {
        detector["execution_mode"]
        for detector in process_config["pipeline"]["detectors"]
    } == {"process"}
    assert {
        tracker["execution_mode"]
        for tracker in process_config["pipeline"]["trackers"]
    } == {"thread"}
    assert process_config["server"]["execution_mode"] == "thread"

    thread_dets = thread_config["pipeline"]["detectors"]
    assert {d["execution_mode"] for d in thread_dets} == {"thread"}


def test_prepare_configs_shared_pool_with_detector_process_only(tmp_path: Path):
    args = Namespace(
        base_config="configs/multi_videos.json",
        out_dir=str(tmp_path),
        max_cameras=4,
        allow_missing=False,
        enable_server=False,
        repeat_cameras=True,
        num_detection_threads=1,
        shared_detector_pool=True,
        detector_process_only=True,
        capture_process_also=False,
        target_fps=30,
    )

    manifest = prepare_configs(args)
    process_config = json.loads((tmp_path / "bench_04cam_process.json").read_text(encoding="utf-8"))
    thread_config = json.loads((tmp_path / "bench_04cam_thread.json").read_text(encoding="utf-8"))

    assert manifest["shared_detector_pool"] is True
    assert manifest["detector_process_only"] is True
    assert manifest["capture_process_also"] is False

    pd = process_config["pipeline"]["detectors"]
    assert len(pd) == 1
    assert pd[0]["source_ids"] == [0, 1, 2, 3]
    assert pd[0]["execution_mode"] == "process"
    td = thread_config["pipeline"]["detectors"]
    assert len(td) == 1
    assert td[0]["source_ids"] == [0, 1, 2, 3]
    assert td[0]["execution_mode"] == "thread"
    assert all(s["execution_mode"] == "thread" for s in process_config["pipeline"]["sources"])
    assert process_config["server"]["execution_mode"] == "thread"


def test_prepare_configs_capture_and_detector_process_only(tmp_path: Path):
    args = Namespace(
        base_config="configs/multi_videos.json",
        out_dir=str(tmp_path),
        max_cameras=4,
        allow_missing=False,
        enable_server=False,
        repeat_cameras=True,
        num_detection_threads=1,
        shared_detector_pool=True,
        detector_process_only=True,
        capture_process_also=True,
        target_fps=30,
    )

    manifest = prepare_configs(args)
    process_config = json.loads((tmp_path / "bench_04cam_process.json").read_text(encoding="utf-8"))

    assert manifest["capture_process_also"] is True
    assert all(s["execution_mode"] == "process" for s in process_config["pipeline"]["sources"])
    assert all(d["execution_mode"] == "process" for d in process_config["pipeline"]["detectors"])
    assert all(t["execution_mode"] == "thread" for t in process_config["pipeline"]["trackers"])
    assert process_config["server"]["execution_mode"] == "thread"
