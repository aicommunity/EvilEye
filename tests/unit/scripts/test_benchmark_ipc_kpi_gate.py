from argparse import Namespace
from pathlib import Path

from scripts.benchmark_ipc_kpi import parse_log, evaluate_gate


def test_parse_log_extracts_pipeline_and_fps(tmp_path: Path):
    log_path = tmp_path / "run.log"
    log_path.write_text(
        "\n".join(
            [
                "INFO PerfDiag(Pipeline): loop=1, total=10.0ms, ...",
                "INFO PerfDiag(Pipeline): loop=2, total=20.0ms, ...",
                "INFO Capture perf: FPS=12.50",
                "DEBUG {'total_memory_usage_mb': 321.0}",
            ]
        ),
        encoding="utf-8",
    )
    metrics = parse_log(log_path)
    assert metrics["p95_pipeline_ms"] >= 10.0
    assert metrics["pipeline_hz_est"] > 0.0
    assert metrics["pipeline_samples"] == 2
    assert metrics["avg_capture_fps"] == 12.5
    assert metrics["capture_fps_samples"] == 1
    assert metrics["max_rss_mb"] == 321.0


def test_evaluate_gate_detects_failures():
    metrics = {
        "errors": 1,
        "tracebacks": 0,
        "stop_timeouts": 0,
        "force_kills": 0,
        "restart_events": 0,
        "p95_pipeline_ms": 10.0,
        "max_rss_mb": 200.0,
    }
    args = Namespace(
        max_errors=0,
        max_tracebacks=0,
        max_stop_timeouts=0,
        max_force_kills=0,
        max_restarts=10,
        max_p95_pipeline_ms=100.0,
        max_rss_mb=1024.0,
        min_pipeline_samples=1,
    )
    ok, reasons = evaluate_gate(metrics, args)
    assert not ok
    assert reasons
