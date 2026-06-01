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

    source_count = max(1, int(camera_count or 1))
    fps_values: list[float] = []
    previous_ts = samples[0][0]
    for timestamp, updates in samples[1:]:
        elapsed = timestamp - previous_ts
        previous_ts = timestamp
        if elapsed <= 0:
            continue
        fps_values.append(sum(updates.values()) / source_count / elapsed)
    return _avg(fps_values)


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

    return {
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
        "detector_fps_est": _coalesce_float(detector_fps_diag, _fps_from_ms(_avg(stage_ms.get("detectors", [])))),
        "tracker_fps_est": _coalesce_float(tracker_fps_diag, _fps_from_ms(_avg(stage_ms.get("trackers", [])))),
        "source_fps_est": _fps_from_ms(_avg(stage_ms.get("sources", []))),
        "avg_capture_fps": _coalesce_float(_avg(capture_fps_values), capture_fps_diag),
        "visual_fps_est": _coalesce_float(visual_fps_diag, _avg(visual_fps_values)),
        "controller_samples": len(controller_total_ms),
    }


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
                "log": str(log_path.relative_to(_repo_root())),
                "samples": str((out_dir / "samples" / f"{stem}.csv").relative_to(_repo_root())),
            }
        )
    return runs


def collect_rows(out_dir: Path, *, warmup_windows: int = DEFAULT_WARMUP_WINDOWS) -> list[dict[str, Any]]:
    repo_root = _repo_root()
    rows: list[dict[str, Any]] = []
    for run in _discover_runs(out_dir):
        log_path = repo_root / str(run["log"])
        if not log_path.exists():
            continue
        sample_path = repo_root / str(run.get("samples", ""))
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


def _markdown_table(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Камер | Режим | Захват, кадр/с | Обнаружение, кадр/с | Отслеживание, кадр/с | Визуализация, кадр/с | p95 цикла, мс | CPU, % | RAM, ГБ | GPU, % | GPU-RAM, ГБ | Ошибки | Валиден |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| {cams} | {mode} | {cap} | {det} | {trk} | {vis} | {p95} | {cpu} | {ram} | {gpu_util} | {gpu} | {err} | {valid} |".format(
                cams=row.get("camera_count"),
                mode=row.get("mode_label"),
                cap=_fmt(row.get("avg_capture_fps")),
                det=_fmt(row.get("detector_fps_est")),
                trk=_fmt(row.get("tracker_fps_est")),
                vis=_fmt(row.get("visual_fps_est")),
                p95=_fmt(row.get("p95_pipeline_ms")),
                cpu=_fmt(row.get("avg_cpu_percent")),
                ram=_fmt(row.get("max_ram_gb")),
                gpu_util=_fmt(row.get("avg_gpu_util_percent")),
                gpu=_fmt(row.get("max_gpu_ram_gb")),
                err=row.get("errors", 0),
                valid="да" if row.get("valid_run") else "нет",
            )
        )
    return lines


def _efficiency_lines(rows: list[dict[str, Any]]) -> list[str]:
    by_camera: dict[int, dict[str, dict[str, Any]]] = {}
    for row in rows:
        by_camera.setdefault(int(row["camera_count"]), {})[str(row["mode"])] = row

    lines = [
        "| Камер | Ускорение по обнаружению | Ускорение по отслеживанию | Снижение p95 задержки |",
        "| ---: | ---: | ---: | ---: |",
    ]
    for cameras in sorted(by_camera):
        pair = by_camera[cameras]
        thread = pair.get("thread")
        process = pair.get("process")
        if not thread or not process:
            continue

        def speed(base_row: dict[str, Any], candidate_row: dict[str, Any], metric: str) -> str:
            base = _safe_float(base_row.get(metric))
            candidate = _safe_float(candidate_row.get(metric))
            if not base or not candidate:
                return "-"
            return f"{candidate / base:.2f}x".replace(".", ",")

        base_p95 = _safe_float(thread.get("p95_pipeline_ms"))
        proc_p95 = _safe_float(process.get("p95_pipeline_ms"))
        if base_p95 and proc_p95:
            latency_delta = f"{((base_p95 - proc_p95) / base_p95) * 100.0:.1f}%".replace(".", ",")
        else:
            latency_delta = "-"

        lines.append(
            f"| {cameras} | {speed(thread, process, 'detector_fps_est')} | {speed(thread, process, 'tracker_fps_est')} | {latency_delta} |"
        )
    return lines


def write_report(rows: list[dict[str, Any]], path: Path, plots: list[Path], *, warmup_windows: int) -> None:
    lines = [
        "# Отчёт о сравнении однопроцессного и мультипроцессного режимов",
        "",
        "## Методика",
        "Для каждой конфигурации используется одинаковый набор видеоисточников, модель и параметры FPS. "
        "Сравниваются режимы `thread` и `process`; GUI выключен, метрики собираются из `PerfDiag` и системных сэмплов runner-а.",
        f"Первые диагностические окна прогрева отброшены: {warmup_windows}.",
        "",
        "## Сводная таблица",
        "",
        *_markdown_table(rows),
        "",
        "## Оценка эффективности",
        "",
        *_efficiency_lines(rows),
        "",
        "## Графики",
    ]
    if plots:
        for plot in plots:
            lines.append(f"- `{plot.as_posix()}`")
    else:
        lines.append("- Графики не построены: нет достаточного набора метрик.")
    lines.extend(
        [
            "",
            "## Примечания",
            "- `Захват` — среднее по строкам `FPS=...` в логе; при отсутствии — оценка по окнам `PerfDiag(DetectorsIn)` (прирост кадров на вход детектора на одну камеру за интервал).",
            "- `Обнаружение`, `Отслеживание` и `Визуализация` вычисляются как оценки FPS по диагностическим временам стадий.",
            "- `GPU-RAM` заполняется только если во время запуска доступна команда `nvidia-smi`.",
            "- При интерпретации учитывайте ошибки, перезапуски и таймауты: такие прогоны нельзя считать валидным доказательством ускорения.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


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


def render(args: argparse.Namespace) -> list[dict[str, Any]]:
    repo_root = _repo_root()
    out_dir = (repo_root / args.out_dir).resolve()
    rows = collect_rows(out_dir, warmup_windows=args.warmup_windows)
    if not rows:
        raise SystemExit(
            "Не найдены логи benchmark. Сначала запустите scripts/run_multiprocessing_benchmark.py "
            "или укажите --out-dir с каталогом результатов."
        )

    results_csv = out_dir / "results.csv"
    report_md = out_dir / "report.md"
    plots = write_plots(rows, out_dir / "plots")
    write_results_csv(rows, results_csv)
    write_report(
        rows,
        report_md,
        [path.relative_to(repo_root) for path in plots],
        warmup_windows=args.warmup_windows,
    )
    print(f"CSV: {results_csv.relative_to(repo_root)}")
    print(f"Отчёт: {report_md.relative_to(repo_root)}")
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
