from pathlib import Path

from scripts.render_multiprocessing_benchmark_report import parse_log


def test_parse_log_uses_pipeline_sources_as_capture_fallback(tmp_path: Path):
    log_path = tmp_path / "run.log"
    log_path.write_text(
        "\n".join(
            [
                "# camera_count: 2",
                "# mode: process",
                "2026-05-13 14:00:00,000 - INFO - PerfDiag(DetectorsIn): window=30 updates={0: 30, 1: 30} repeats={}",
                "2026-05-13 14:00:00,000 - INFO - PerfDiag(TrackersIn): window=30 updates={0: 6, 1: 6} repeats={}",
                "2026-05-13 14:00:00,000 - INFO - PerfDiag(TrackersOut): window=30 updates={0: 3, 1: 3} repeats={}",
                "INFO PerfDiag(Pipeline): loop=30, total=100.0ms, sources=10.0ms(len=2), detectors=50.0ms(len=2), trackers=20.0ms(len=2)",
                "2026-05-13 14:00:03,000 - INFO - PerfDiag(DetectorsIn): window=60 updates={0: 30, 1: 30} repeats={}",
                "2026-05-13 14:00:03,000 - INFO - PerfDiag(TrackersIn): window=60 updates={0: 6, 1: 6} repeats={}",
                "2026-05-13 14:00:03,000 - INFO - PerfDiag(TrackersOut): window=60 updates={0: 3, 1: 3} repeats={}",
                "INFO PerfDiag(Pipeline): loop=60, total=80.0ms, sources=5.0ms(len=2), detectors=25.0ms(len=2), trackers=10.0ms(len=2)",
                "2026-05-13 14:00:03,000 - INFO - PerfDiag: loop=30, frames=2, pipeline_ms=1.0, select_ms=1.0, proc_ms=1.0, publish_ms=1.0, viz_ms=5.0, total_ms=10.0",
                "2026-05-13 14:00:06,000 - INFO - PerfDiag: loop=60, frames=2, pipeline_ms=1.0, select_ms=1.0, proc_ms=1.0, publish_ms=1.0, viz_ms=5.0, total_ms=10.0",
            ]
        ),
        encoding="utf-8",
    )

    metrics = parse_log(log_path, warmup_windows=0)

    assert metrics["avg_capture_fps"] == 10.0
    assert metrics["detector_fps_est"] == 2.0
    assert metrics["tracker_fps_est"] == 1.0
    assert metrics["visual_fps_est"] == 10.0
    assert metrics["pipeline_samples"] == 2
