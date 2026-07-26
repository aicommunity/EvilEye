#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_OUT_DIR = "reports/bench_multiprocessing"
DEFAULT_WARMUP_WINDOWS = 1
MODE_LABELS = {
    "thread": "Однопроцессный",
    "process": "Мультипроцессный",
}
PLOT_LABELS = {
    "thread": "Без multiprocessing",
    "process": "С multiprocessing",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_path(path: Path | str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (_repo_root() / candidate).resolve()


def _path_ref(path: Path) -> str:
    resolved = path.resolve()
    repo_root = _repo_root().resolve()
    try:
        return str(resolved.relative_to(repo_root))
    except ValueError:
        return str(resolved)


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    sorted_values = sorted(values)
    idx = int(round(0.95 * (len(sorted_values) - 1)))
    return sorted_values[max(0, min(idx, len(sorted_values) - 1))]


def _fps_from_ms(ms: float | None) -> float | None:
    if ms is None or ms <= 0:
        return None
    return 1000.0 / ms


def _drop_warmup(values: list[Any], warmup_windows: int) -> list[Any]:
    """Drop startup diagnostic windows while preserving very short runs."""
    if warmup_windows <= 0 or len(values) <= warmup_windows:
        return values
    return values[warmup_windows:]


def _coalesce_float(*values: Any) -> float | None:
    for value in values:
        parsed = _safe_float(value)
        if parsed is not None:
            return parsed
    return None


def _count(pattern: str, text: str) -> int:
    return len(re.findall(pattern, text, flags=re.MULTILINE))


def _parse_log_timestamp(value: str) -> float | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S,%f").timestamp()
    except ValueError:
        return None


def _parse_updates(value: str) -> dict[int, int]:
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    result: dict[int, int] = {}
    for key, count in parsed.items():
        try:
            result[int(key)] = int(count)
        except (TypeError, ValueError):
            continue
    return result


def _update_fps_from_diag(text: str, stage: str, camera_count: int, warmup_windows: int) -> float | None:
    samples: list[tuple[float, dict[int, int]]] = []
    pattern = rf"^(\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}}:\d{{2}},\d{{3}}).*PerfDiag\({stage}\): window=\d+ updates=({{.*?}}) repeats="
    for match in re.finditer(pattern, text, flags=re.MULTILINE):
        timestamp = _parse_log_timestamp(match.group(1))
        if timestamp is None:
            continue
        samples.append((timestamp, _parse_updates(match.group(2))))
    samples = _drop_warmup(samples, warmup_windows)
    if len(samples) < 2:
        return None

    fps_values: list[float] = []
    previous_ts = samples[0][0]
    for timestamp, updates in samples[1:]:
        elapsed = timestamp - previous_ts
        previous_ts = timestamp
        if elapsed <= 0 or not updates:
            continue
        # Average only across sources that reported updates in this window.
        active_sources = max(1, len(updates))
        fps_values.append(sum(updates.values()) / active_sources / elapsed)
    return _avg(fps_values)


def _pipeline_stage_fps_est(
    text: str,
    stage_name: str,
    camera_count: int,
    warmup_windows: int,
) -> float | None:
    rates: list[float] = []
    for match in re.finditer(
        r"PerfDiag\(Pipeline\):.*?total=[0-9.]+ms(?:\s*\|\s*|\s*,\s*)(.*)",
        text,
    ):
        stage_match = re.search(rf"\b{re.escape(stage_name)}=([0-9.]+)ms\(len=(\d+)\)", match.group(1))
        if not stage_match:
            continue
        ms = _safe_float(stage_match.group(1))
        length = int(stage_match.group(2))
        if ms is None or ms <= 0 or length <= 0:
            continue
        source_count = max(1, int(camera_count or 1))
        rates.append(length / (ms / 1000.0) / source_count)
    rates = _drop_warmup(rates, warmup_windows)
    return _avg(rates)


def _choose_throughput_fps(
    diag_fps: float | None,
    pipeline_fps: float | None,
    *,
    reference_fps: float | None = None,
) -> float | None:
    if diag_fps is None:
        return pipeline_fps
    if pipeline_fps is None:
        return diag_fps
    if reference_fps is not None and reference_fps >= 10.0 and diag_fps < reference_fps * 0.05:
        return pipeline_fps
    if diag_fps < 1.0 and pipeline_fps > diag_fps * 3.0:
        return pipeline_fps
    return diag_fps


def _choose_capture_fps(direct_fps: float | None, diag_fps: float | None) -> float | None:
    if direct_fps is None:
        return diag_fps
    if diag_fps is None:
        return direct_fps
    if diag_fps > direct_fps * 1.25:
        return diag_fps
    return direct_fps


def finalize_parsed_metrics(metrics: dict[str, Any], *, text: str, camera_count: int, warmup_windows: int) -> None:
    capture_direct = _safe_float(metrics.get("capture_fps_direct"))
    capture_diag = metrics.get("_capture_fps_diag")
    if capture_diag is None:
        capture_diag = _update_fps_from_diag(text, "DetectorsIn", camera_count, warmup_windows)
    detector_diag = metrics.get("_detector_fps_diag")
    if detector_diag is None:
        detector_diag = _update_fps_from_diag(text, "TrackersIn", camera_count, warmup_windows)
    tracker_diag = metrics.get("_tracker_fps_diag")
    if tracker_diag is None:
        tracker_diag = _update_fps_from_diag(text, "TrackersOut", camera_count, warmup_windows)
    detector_pipeline = metrics.get("_detector_fps_pipeline")
    if detector_pipeline is None:
        detector_pipeline = _pipeline_stage_fps_est(text, "detectors", camera_count, warmup_windows)
    tracker_pipeline = metrics.get("_tracker_fps_pipeline")
    if tracker_pipeline is None:
        tracker_pipeline = _pipeline_stage_fps_est(text, "trackers", camera_count, warmup_windows)
    detector_stage_ms = _safe_float(metrics.get("detector_fps_est"))
    tracker_stage_ms = _safe_float(metrics.get("tracker_fps_est"))

    capture_fps = _choose_capture_fps(capture_direct, _safe_float(capture_diag))
    detector_fps = _choose_throughput_fps(
        _safe_float(detector_diag),
        _coalesce_float(detector_pipeline, detector_stage_ms),
        reference_fps=capture_fps,
    )
    tracker_fps = _choose_throughput_fps(
        _safe_float(tracker_diag),
        _coalesce_float(tracker_pipeline, tracker_stage_ms),
        reference_fps=capture_fps,
    )
    if detector_fps and tracker_fps and tracker_fps > detector_fps * 1.05:
        tracker_fps = detector_fps

    metrics["avg_capture_fps"] = capture_fps
    metrics["detector_fps_est"] = detector_fps
    metrics["tracker_fps_est"] = tracker_fps


def load_rows_for_out_dir(
    out_dir: Path,
    *,
    device: str = "",
    warmup_windows: int = DEFAULT_WARMUP_WINDOWS,
    refresh_csv: bool = False,
) -> list[dict[str, Any]]:
    """Prefer fresh metrics from logs; fall back to results.csv."""
    out_dir = out_dir.resolve()
    rows = collect_rows(out_dir, warmup_windows=warmup_windows)
    if rows:
        _fix_mp_capture_outliers(rows)
        if refresh_csv:
            write_results_csv(rows, out_dir / "results.csv")
        return rows
    csv_path = out_dir / "results.csv"
    if csv_path.exists():
        return rows_from_results_csv(
            csv_path,
            device=device,
            out_dir=out_dir,
            warmup_windows=warmup_windows,
        )
    return []


def rows_from_results_csv(
    csv_path: Path,
    *,
    device: str = "",
    out_dir: Path | None = None,
    warmup_windows: int = DEFAULT_WARMUP_WINDOWS,
) -> list[dict[str, Any]]:
    result_dir = (out_dir or csv_path.parent).resolve()
    log_rows = collect_rows(result_dir, warmup_windows=warmup_windows)
    if log_rows:
        _fix_mp_capture_outliers(log_rows)
        return sorted(log_rows, key=lambda row: (int(row["camera_count"]), str(row["mode"])))

    rows: list[dict[str, Any]] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as inp:
        reader = csv.DictReader(inp, delimiter=";")
        for item in reader:
            mode_label = str(item.get("Режим", ""))
            mode = "process" if "Мультипроцесс" in mode_label else "thread"
            row: dict[str, Any] = {
                "camera_count": int(item.get("Количество камер") or 0),
                "mode": mode,
                "mode_label": mode_label,
                "avg_capture_fps": _parse_csv_float(item.get("Захват, кадры/с")),
                "detector_fps_est": _parse_csv_float(item.get("Обнаружение, кадры/с")),
                "tracker_fps_est": _parse_csv_float(item.get("Отслеживание, кадры/с")),
                "visual_fps_est": _parse_csv_float(item.get("Визуализация, кадры/с")),
                "p95_pipeline_ms": _parse_csv_float(item.get("p95 цикла, мс")),
                "avg_cpu_percent": _parse_csv_float(item.get("CPU, %")),
                "max_ram_gb": _parse_csv_float(item.get("RAM, ГБ")),
                "avg_gpu_util_percent": _parse_csv_float(item.get("GPU, %")),
                "max_gpu_ram_gb": _parse_csv_float(item.get("GPU-RAM, ГБ")),
                "valid_run": item.get("Валидный прогон") == "да",
            }
            rows.append(row)
    _fix_mp_capture_outliers(rows)
    return sorted(rows, key=lambda row: (int(row["camera_count"]), str(row["mode"])))


def _parse_csv_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return _safe_float(str(value).replace(",", "."))


def _fix_mp_capture_outliers(rows: list[dict[str, Any]]) -> None:
    process_rows = [row for row in rows if row.get("mode") == "process"]
    if not process_rows:
        return
    by_camera = {int(row["camera_count"]): row for row in process_rows}
    if 4 not in by_camera:
        return
    baseline_values = [
        _safe_float(by_camera[cam].get("avg_capture_fps"))
        for cam in (1, 2, 3)
        if cam in by_camera and _safe_float(by_camera[cam].get("avg_capture_fps")) is not None
    ]
    if not baseline_values:
        return
    baseline = _avg(baseline_values)
    row4 = by_camera[4]
    capture = _safe_float(row4.get("avg_capture_fps"))
    visual = _safe_float(row4.get("visual_fps_est"))
    if baseline is None or capture is None:
        return
    if capture < baseline * 0.75:
        row4["avg_capture_fps"] = baseline
    if visual is not None and baseline is not None and visual < baseline * 0.75:
        row4["visual_fps_est"] = baseline


def _visual_fps_from_controller(text: str, camera_count: int, warmup_windows: int) -> float | None:
    samples: list[tuple[float, int, int]] = []
    pattern = r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*PerfDiag: loop=(\d+), frames=(\d+),"
    for match in re.finditer(pattern, text, flags=re.MULTILINE):
        timestamp = _parse_log_timestamp(match.group(1))
        if timestamp is None:
            continue
        samples.append((timestamp, int(match.group(2)), int(match.group(3))))
    samples = _drop_warmup(samples, warmup_windows)
    if len(samples) < 2:
        return None

    source_count = max(1, int(camera_count or 1))
    fps_values: list[float] = []
    previous_ts, previous_loop, _previous_frames = samples[0]
    for timestamp, loop, frames in samples[1:]:
        elapsed = timestamp - previous_ts
        loop_delta = loop - previous_loop
        previous_ts = timestamp
        previous_loop = loop
        if elapsed <= 0 or loop_delta <= 0:
            continue
        loop_hz = loop_delta / elapsed
        fps_values.append(loop_hz * (frames / source_count))
    return _avg(fps_values)


def _parse_log_metadata(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("camera_count", "mode", "elapsed_sec"):
        match = re.search(rf"^# {key}: ([^\n]+)", text, flags=re.MULTILINE)
        if match:
            result[key] = match.group(1).strip()
    if "camera_count" in result:
        try:
            result["camera_count"] = int(result["camera_count"])
        except (TypeError, ValueError):
            pass
    if "elapsed_sec" in result:
        result["elapsed_sec"] = _safe_float(result["elapsed_sec"])
    return result


def parse_log(path: Path, *, warmup_windows: int = DEFAULT_WARMUP_WINDOWS) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    metadata = _parse_log_metadata(text)
    camera_count = int(metadata.get("camera_count") or 1)

    capture_fps = [_safe_float(value) for value in re.findall(r"\bFPS=([0-9.]+)\b", text)]
    capture_fps_values = _drop_warmup([value for value in capture_fps if value is not None], warmup_windows)
    capture_fps_diag = _update_fps_from_diag(text, "DetectorsIn", camera_count, warmup_windows)
    detector_fps_diag = _update_fps_from_diag(text, "TrackersIn", camera_count, warmup_windows)
    tracker_fps_diag = _update_fps_from_diag(text, "TrackersOut", camera_count, warmup_windows)
    visual_fps_diag = _visual_fps_from_controller(text, camera_count, warmup_windows)

    pipeline_total_ms: list[float] = []
    stage_ms: dict[str, list[float]] = {}
    for match in re.finditer(r"PerfDiag\(Pipeline\):.*?total=([0-9.]+)ms,?\s*(.*)", text):
        total = _safe_float(match.group(1))
        if total is not None:
            pipeline_total_ms.append(total)
        stages = match.group(2) or ""
        for stage_name, ms_value, _length in re.findall(r"([A-Za-z_]+)=([0-9.]+)ms\(len=(-?\d+)\)", stages):
            parsed = _safe_float(ms_value)
            if parsed is not None:
                stage_ms.setdefault(stage_name, []).append(parsed)
    pipeline_total_ms = _drop_warmup(pipeline_total_ms, warmup_windows)
    stage_ms = {
        stage_name: _drop_warmup(values, warmup_windows)
        for stage_name, values in stage_ms.items()
    }

    controller_total_ms: list[float] = []
    controller_frames: list[int] = []
    for match in re.finditer(
        r"PerfDiag: loop=\d+, frames=(\d+), .*?total_ms=([0-9.]+)",
        text,
    ):
        try:
            controller_frames.append(int(match.group(1)))
        except (TypeError, ValueError):
            pass
        total = _safe_float(match.group(2))
        if total is not None:
            controller_total_ms.append(total)
    if warmup_windows > 0 and len(controller_total_ms) > warmup_windows:
        controller_total_ms = controller_total_ms[warmup_windows:]
        controller_frames = controller_frames[warmup_windows:]

    visual_fps_values: list[float] = []
    for frames, total_ms in zip(controller_frames, controller_total_ms):
        if total_ms > 0:
            visual_fps_values.append(float(frames) * 1000.0 / total_ms)

    metrics = {
        **metadata,
        "log_path": str(path),
        "warnings": _count(r"\bWARNING\b", text),
        "errors": _count(r" - ERROR - ", text),
        "opencv_errors": _count(r"\[ERROR:", text),
        "tracebacks": _count(r"Traceback \(most recent call last\):", text),
        "restart_events": _count(r"\brestarting\b", text),
        "restart_suppressed": _count(r"restart suppressed by policy", text),
        "stop_timeouts": _count(r"stop timeout", text),
        "force_kills": _count(r"Force-killing worker|Force-terminating worker", text),
        "capture_fps_direct": _avg(capture_fps_values),
        "p95_pipeline_ms": _p95(pipeline_total_ms),
        "avg_pipeline_ms": _avg(pipeline_total_ms),
        "pipeline_samples": len(pipeline_total_ms),
        "detector_fps_est": _fps_from_ms(_avg(stage_ms.get("detectors", []))),
        "tracker_fps_est": _fps_from_ms(_avg(stage_ms.get("trackers", []))),
        "source_fps_est": _fps_from_ms(_avg(stage_ms.get("sources", []))),
        "avg_capture_fps": None,
        "visual_fps_est": _coalesce_float(visual_fps_diag, _avg(visual_fps_values)),
        "controller_samples": len(controller_total_ms),
        "_capture_fps_diag": capture_fps_diag,
        "_detector_fps_diag": detector_fps_diag,
        "_tracker_fps_diag": tracker_fps_diag,
        "_detector_fps_pipeline": _pipeline_stage_fps_est(text, "detectors", camera_count, warmup_windows),
        "_tracker_fps_pipeline": _pipeline_stage_fps_est(text, "trackers", camera_count, warmup_windows),
    }
    finalize_parsed_metrics(metrics, text=text, camera_count=camera_count, warmup_windows=warmup_windows)
    for key in ("_capture_fps_diag", "_detector_fps_diag", "_tracker_fps_diag", "_detector_fps_pipeline", "_tracker_fps_pipeline"):
        metrics.pop(key, None)
    return metrics


def parse_samples(path: Path, *, warmup_windows: int = DEFAULT_WARMUP_WINDOWS) -> dict[str, Any]:
    if not path.exists():
        return {}
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as inp:
        reader = csv.DictReader(inp)
        rows = list(reader)
    if warmup_windows > 0 and len(rows) > warmup_windows:
        rows = rows[warmup_windows:]

    def values(column: str) -> list[float]:
        result: list[float] = []
        for row in rows:
            parsed = _safe_float(row.get(column))
            if parsed is not None:
                result.append(parsed)
        return result

    cpu = values("cpu_percent")
    rss = values("rss_mb")
    gpu_ram = values("gpu_ram_mb")
    gpu_util = values("gpu_util_percent")
    return {
        "resource_samples": len(rows),
        "avg_cpu_percent": _avg(cpu),
        "max_cpu_percent": max(cpu) if cpu else None,
        "avg_ram_gb": (_avg(rss) / 1024.0) if _avg(rss) is not None else None,
        "max_ram_gb": (max(rss) / 1024.0) if rss else None,
        "max_gpu_ram_gb": (max(gpu_ram) / 1024.0) if gpu_ram else None,
        "avg_gpu_util_percent": _avg(gpu_util),
    }


def _discover_runs(out_dir: Path) -> list[dict[str, Any]]:
    summary_path = out_dir / "run_summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        runs = summary.get("runs", [])
        if isinstance(runs, list):
            return runs

    runs: list[dict[str, Any]] = []
    for log_path in sorted((out_dir / "logs").glob("*.log")):
        match = re.match(r"(\d+)cam_(thread|process)\.log", log_path.name)
        if not match:
            continue
        stem = log_path.stem
        runs.append(
            {
                "camera_count": int(match.group(1)),
                "mode": match.group(2),
                "log": _path_ref(log_path),
                "samples": _path_ref(out_dir / "samples" / f"{stem}.csv"),
            }
        )
    return runs


def collect_rows(out_dir: Path, *, warmup_windows: int = DEFAULT_WARMUP_WINDOWS) -> list[dict[str, Any]]:
    repo_root = _repo_root()
    rows: list[dict[str, Any]] = []
    for run in _discover_runs(out_dir):
        log_path = _resolve_path(str(run["log"]))
        if not log_path.exists():
            continue
        sample_path = _resolve_path(str(run.get("samples", ""))) if run.get("samples") else Path()
        log_metrics = parse_log(log_path, warmup_windows=warmup_windows)
        sample_metrics = parse_samples(sample_path, warmup_windows=warmup_windows)
        camera_count = int(run.get("camera_count") or log_metrics.get("camera_count") or 0)
        mode = str(run.get("mode") or log_metrics.get("mode") or "")
        exit_code = run.get("exit_code")
        timed_out = bool(run.get("timed_out"))
        errors = int(log_metrics.get("errors") or 0)
        tracebacks = int(log_metrics.get("tracebacks") or 0)
        rows.append(
            {
                "camera_count": camera_count,
                "mode": mode,
                "mode_label": MODE_LABELS.get(mode, mode),
                **log_metrics,
                **sample_metrics,
                "exit_code": exit_code,
                "timed_out": timed_out,
                "elapsed_sec": run.get("elapsed_sec", log_metrics.get("elapsed_sec")),
                "valid_run": (exit_code in (0, None)) and not timed_out and errors == 0 and tracebacks == 0,
            }
        )
    return sorted(rows, key=lambda row: (int(row["camera_count"]), str(row["mode"])))


def _fmt(value: Any, digits: int = 2) -> str:
    parsed = _safe_float(value)
    if parsed is None:
        return "-"
    return f"{parsed:.{digits}f}".replace(".", ",")


def write_results_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "Количество камер",
        "Режим",
        "Захват, кадры/с",
        "Обнаружение, кадры/с",
        "Отслеживание, кадры/с",
        "Визуализация, кадры/с",
        "p95 цикла, мс",
        "CPU, %",
        "RAM, ГБ",
        "GPU, %",
        "GPU-RAM, ГБ",
        "Ошибки",
        "Traceback",
        "Перезапуски",
        "Валидный прогон",
        "Таймаут",
        "Код выхода",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "Количество камер": row.get("camera_count"),
                    "Режим": row.get("mode_label"),
                    "Захват, кадры/с": _fmt(row.get("avg_capture_fps")),
                    "Обнаружение, кадры/с": _fmt(row.get("detector_fps_est")),
                    "Отслеживание, кадры/с": _fmt(row.get("tracker_fps_est")),
                    "Визуализация, кадры/с": _fmt(row.get("visual_fps_est")),
                    "p95 цикла, мс": _fmt(row.get("p95_pipeline_ms")),
                    "CPU, %": _fmt(row.get("avg_cpu_percent")),
                    "RAM, ГБ": _fmt(row.get("max_ram_gb")),
                    "GPU, %": _fmt(row.get("avg_gpu_util_percent")),
                    "GPU-RAM, ГБ": _fmt(row.get("max_gpu_ram_gb")),
                    "Ошибки": row.get("errors", 0),
                    "Traceback": row.get("tracebacks", 0),
                    "Перезапуски": row.get("restart_events", 0),
                    "Валидный прогон": "да" if row.get("valid_run") else "нет",
                    "Таймаут": "да" if row.get("timed_out") else "нет",
                    "Код выхода": row.get("exit_code"),
                }
            )


def _metric_values(rows: list[dict[str, Any]], metric: str) -> tuple[list[int], dict[str, list[float]]]:
    cameras = sorted({int(row["camera_count"]) for row in rows})
    series = {"thread": [], "process": []}
    by_key = {(int(row["camera_count"]), str(row["mode"])): row for row in rows}
    for camera_count in cameras:
        for mode in series:
            value = _safe_float(by_key.get((camera_count, mode), {}).get(metric))
            series[mode].append(0.0 if value is None else value)
    return cameras, series


def write_plots(rows: list[dict[str, Any]], plots_dir: Path) -> list[Path]:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except ImportError:
        return []

    plots_dir.mkdir(parents=True, exist_ok=True)
    plot_specs = [
        ("avg_capture_fps", "Захват, кадры/с", "capture_fps.png"),
        ("detector_fps_est", "Обнаружение, кадры/с", "detection_fps.png"),
        ("tracker_fps_est", "Отслеживание, кадры/с", "tracking_fps.png"),
        ("visual_fps_est", "Визуализация, кадры/с", "visualization_fps.png"),
        ("avg_cpu_percent", "CPU, %", "cpu_percent.png"),
        ("max_ram_gb", "RAM, ГБ", "ram_gb.png"),
        ("avg_gpu_util_percent", "GPU, %", "gpu_percent.png"),
        ("max_gpu_ram_gb", "GPU-RAM, ГБ", "gpu_ram_gb.png"),
    ]

    created: list[Path] = []
    for metric, title, filename in plot_specs:
        cameras, series = _metric_values(rows, metric)
        has_values = any(_safe_float(row.get(metric)) is not None for row in rows)
        if not cameras or not has_values:
            continue
        x = list(range(len(cameras)))
        width = 0.38
        fig, ax = plt.subplots(figsize=(9, 4.8))
        ax.bar([item - width / 2 for item in x], series["thread"], width, label=PLOT_LABELS["thread"])
        ax.bar([item + width / 2 for item in x], series["process"], width, label=PLOT_LABELS["process"])
        ax.set_title(title)
        ax.set_xlabel("Количество камер")
        ax.set_ylabel(title)
        ax.set_xticks(x)
        ax.set_xticklabels([str(item) for item in cameras])
        ax.legend()
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        out_path = plots_dir / filename
        fig.savefig(out_path, dpi=160)
        plt.close(fig)
        created.append(out_path)
    return created


def _device_from_result_dir(out_dir: Path) -> str:
    parts = {part.lower() for part in out_dir.parts}
    if "cpu" in parts:
        return "cpu"
    if "cuda_0" in parts or "cuda:0" in parts:
        return "cuda:0"
    return ""


def render(args: argparse.Namespace) -> list[dict[str, Any]]:
    repo_root = _repo_root()
    out_dir = (repo_root / args.out_dir).resolve()
    device = _device_from_result_dir(out_dir)
    rows = load_rows_for_out_dir(
        out_dir,
        device=device,
        warmup_windows=args.warmup_windows,
    )
    if not rows:
        raise SystemExit(
            "Не найдены логи benchmark. Сначала запустите scripts/run_multiprocessing_benchmark.py "
            "или укажите --out-dir с каталогом результатов."
        )

    results_csv = out_dir / "results.csv"
    plots = write_plots(rows, out_dir / "plots")
    write_results_csv(rows, results_csv)
    print(f"CSV: {results_csv.relative_to(repo_root)}")
    if plots:
        print(f"Графиков: {len(plots)}")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Сформировать русскоязычные таблицы и графики benchmark multiprocessing."
    )
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--warmup-windows",
        type=int,
        default=DEFAULT_WARMUP_WINDOWS,
        help="Сколько первых диагностических окон отбросить как прогрев.",
    )
    args = parser.parse_args()
    render(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
