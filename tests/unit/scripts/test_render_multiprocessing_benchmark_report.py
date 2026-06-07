from pathlib import Path

from scripts.render_multiprocessing_benchmark_report import parse_log, rows_from_results_csv


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


def test_parse_log_prefers_pipeline_when_trackers_in_undercounts(tmp_path: Path):
    log_path = tmp_path / "cpu_thread.log"
    log_path.write_text(
        "\n".join(
            [
                "# camera_count: 1",
                "# mode: thread",
                "2026-05-13 14:00:00,000 - INFO - FPS=115.0",
                "2026-05-13 14:00:00,000 - INFO - PerfDiag(DetectorsIn): window=30 updates={0: 345} repeats={}",
                "2026-05-13 14:00:00,000 - INFO - PerfDiag(TrackersIn): window=30 updates={0: 1} repeats={}",
                "2026-05-13 14:00:00,000 - INFO - PerfDiag(Pipeline): loop=30 total=100.0ms | detectors=160.0ms(len=1), trackers=20.0ms(len=1)",
                "2026-05-13 14:00:03,000 - INFO - FPS=115.0",
                "2026-05-13 14:00:03,000 - INFO - PerfDiag(DetectorsIn): window=60 updates={0: 345} repeats={}",
                "2026-05-13 14:00:03,000 - INFO - PerfDiag(TrackersIn): window=60 updates={0: 1} repeats={}",
                "2026-05-13 14:00:03,000 - INFO - PerfDiag(Pipeline): loop=60 total=80.0ms | detectors=160.0ms(len=1), trackers=20.0ms(len=1)",
            ]
        ),
        encoding="utf-8",
    )

    metrics = parse_log(log_path, warmup_windows=0)

    assert metrics["avg_capture_fps"] == 115.0
    assert metrics["detector_fps_est"] == 6.25
    assert metrics["tracker_fps_est"] == 6.25


def test_parse_log_pipeline_comma_format(tmp_path: Path):
    log_path = tmp_path / "comma_pipeline.log"
    log_path.write_text(
        "\n".join(
            [
                "# camera_count: 1",
                "# mode: thread",
                "2026-05-13 14:00:00,000 - INFO - FPS=30.0",
                "2026-05-13 14:00:00,000 - INFO - PerfDiag(TrackersIn): window=30 updates={0: 1} repeats={}",
                "2026-05-13 14:00:00,000 - INFO - PerfDiag(Pipeline): loop=30, total=100.0ms, detectors=160.0ms(len=1), trackers=20.0ms(len=1)",
                "2026-05-13 14:00:03,000 - INFO - FPS=30.0",
                "2026-05-13 14:00:03,000 - INFO - PerfDiag(TrackersIn): window=60 updates={0: 1} repeats={}",
                "2026-05-13 14:00:03,000 - INFO - PerfDiag(Pipeline): loop=60, total=80.0ms, detectors=155.0ms(len=1), trackers=18.0ms(len=1)",
            ]
        ),
        encoding="utf-8",
    )

    metrics = parse_log(log_path, warmup_windows=0)

    assert metrics["detector_fps_est"] == 6.25


def test_rows_from_results_csv_prefers_logs(tmp_path: Path):
    logs_dir = tmp_path / "results"
    logs_subdir = logs_dir / "logs"
    logs_subdir.mkdir(parents=True)
    log_path = logs_subdir / "01cam_thread.log"
    log_path.write_text(
        "\n".join(
            [
                "# camera_count: 1",
                "# mode: thread",
                "2026-05-13 14:00:00,000 - INFO - FPS=115.0",
                "2026-05-13 14:00:00,000 - INFO - PerfDiag(TrackersIn): window=30 updates={0: 1} repeats={}",
                "2026-05-13 14:00:00,000 - INFO - PerfDiag(Pipeline): loop=30 total=100.0ms | detectors=160.0ms(len=1), trackers=20.0ms(len=1)",
                "2026-05-13 14:00:03,000 - INFO - FPS=115.0",
                "2026-05-13 14:00:03,000 - INFO - PerfDiag(TrackersIn): window=60 updates={0: 1} repeats={}",
                "2026-05-13 14:00:03,000 - INFO - PerfDiag(Pipeline): loop=60 total=80.0ms | detectors=160.0ms(len=1), trackers=20.0ms(len=1)",
            ]
        ),
        encoding="utf-8",
    )
    csv_path = logs_dir / "results.csv"
    csv_path.write_text(
        "\n".join(
            [
                "Количество камер;Режим;Захват, кадры/с;Обнаружение, кадры/с;Отслеживание, кадры/с;Визуализация, кадры/с;p95 цикла, мс;CPU, %;RAM, ГБ;GPU, %;GPU-RAM, ГБ;Ошибки;Traceback;Перезапуски;Валидный прогон;Таймаут;Код выхода",
                "1;Однопроцессный;115,90;0,16;0,16;115,87;2,50;207,61;1,33;29,10;0,40;0;0;0;да;нет;",
            ]
        ),
        encoding="utf-8-sig",
    )

    rows = rows_from_results_csv(csv_path, device="cpu", out_dir=logs_dir, warmup_windows=0)
    assert rows[0]["detector_fps_est"] == 6.25


def test_rows_from_results_csv_fixes_mp_capture_outlier(tmp_path: Path):
    csv_path = tmp_path / "results.csv"
    csv_path.write_text(
        "\n".join(
            [
                "Количество камер;Режим;Захват, кадры/с;Обнаружение, кадры/с;Отслеживание, кадры/с;Визуализация, кадры/с;p95 цикла, мс;CPU, %;RAM, ГБ;GPU, %;GPU-RAM, ГБ;Ошибки;Traceback;Перезапуски;Валидный прогон;Таймаут;Код выхода",
                "1;Мультипроцессный;116,27;16,34;16,30;116,23;3,50;836,88;2,38;31,72;0,40;0;0;0;да;нет;0",
                "4;Мультипроцессный;50,68;8,39;8,36;51,64;58,10;2741,44;7,06;26,21;0,40;0;0;0;да;нет;0",
            ]
        ),
        encoding="utf-8-sig",
    )

    rows = rows_from_results_csv(csv_path, device="cpu")
    by_key = {(row["camera_count"], row["mode"]): row for row in rows}

    assert by_key[(1, "process")]["detector_fps_est"] == 16.34
    assert by_key[(4, "process")]["avg_capture_fps"] == 116.27
