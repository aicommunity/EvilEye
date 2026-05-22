#!/usr/bin/env python3
"""Render poly-videos process vs thread benchmark report."""

from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from poly_mode_compare_lib import COMPARE_CONFIGS, DEFAULT_OUT_DIR, REPO_ROOT

from render_multiprocessing_benchmark_report import (  # noqa: E402
    _avg,
    _fmt,
    _p95,
    _safe_float,
    parse_log,
    parse_samples,
)


def _stats(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "n": 0,
            "mean": None,
            "std": None,
            "min": None,
            "max": None,
            "median": None,
            "cv_pct": None,
        }
    mean = statistics.mean(values)
    std = statistics.pstdev(values) if len(values) > 1 else 0.0
    cv = (std / mean * 100.0) if mean else None
    return {
        "n": len(values),
        "mean": mean,
        "std": std,
        "min": min(values),
        "max": max(values),
        "median": statistics.median(values),
        "cv_pct": cv,
    }


def _fmt_stats(s: dict[str, Any], digits: int = 2) -> str:
    if not s.get("n"):
        return "-"
    mean = s.get("mean")
    std = s.get("std")
    if mean is None:
        return "-"
    if std is None or (isinstance(std, float) and math.isnan(std)):
        return _fmt(mean, digits)
    return f"{_fmt(mean, digits)} ± {_fmt(std, digits)}"


def _delta_pct(a: float | None, b: float | None) -> str:
    """Percent change from a (thread) to b (process): positive = process higher."""
    if a is None or b is None or a == 0:
        return "-"
    return f"{((b - a) / a) * 100.0:+.1f}%".replace(".", ",")


def _discover_runs(out_dir: Path) -> list[dict[str, Any]]:
    summary_path = out_dir / "run_summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        runs = [r for r in summary.get("runs", []) if r.get("kind") != "warmup"]
        if runs:
            return runs
    runs = []
    for log_path in sorted((out_dir / "logs").glob("*_run*.log")):
        match = __import__("re").match(r"(.+)_run(\d+)\.log$", log_path.name)
        if not match:
            continue
        slug = match.group(1)
        spec = next((s for s in COMPARE_CONFIGS if s["slug"] == slug), None)
        if spec is None:
            continue
        runs.append(
            {
                "slug": slug,
                "capture": spec["capture"],
                "mode": spec["mode"],
                "config": spec["config"],
                "run_index": int(match.group(2)),
                "log": str(log_path.relative_to(REPO_ROOT)),
                "samples": str(
                    (out_dir / "samples" / f"{slug}_run{int(match.group(2)):02d}.csv").relative_to(
                        REPO_ROOT
                    )
                ),
            }
        )
    return runs


def collect_run_rows(out_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in _discover_runs(out_dir):
        log_path = REPO_ROOT / str(run["log"])
        if not log_path.exists():
            continue
        sample_path = REPO_ROOT / str(run.get("samples", ""))
        log_m = parse_log(log_path)
        sample_m = parse_samples(sample_path)
        pipeline_hz = None
        avg_ms = _safe_float(log_m.get("avg_pipeline_ms"))
        if avg_ms and avg_ms > 0:
            pipeline_hz = 1000.0 / avg_ms
        rows.append(
            {
                "slug": run.get("slug"),
                "capture": run.get("capture"),
                "mode": run.get("mode"),
                "config": run.get("config"),
                "run_index": run.get("run_index"),
                **log_m,
                **sample_m,
                "pipeline_hz_est": pipeline_hz,
                "exit_code": run.get("exit_code"),
                "timed_out": run.get("timed_out"),
                "success": run.get("success"),
            }
        )
    return rows


def load_output_snapshots(out_dir: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in sorted((out_dir / "artifacts").glob("*_output.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        slug = data.get("slug") or path.stem.replace("_output", "")
        out[slug] = data
    return out


def aggregate_by_group(rows: list[dict[str, Any]], metric: str) -> dict[tuple[str, str], dict[str, Any]]:
    buckets: dict[tuple[str, str], list[float]] = {}
    for row in rows:
        key = (str(row.get("capture")), str(row.get("mode")))
        val = _safe_float(row.get(metric))
        if val is not None:
            buckets.setdefault(key, []).append(val)
    return {k: _stats(v) for k, v in buckets.items()}


def write_results_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "slug",
        "capture",
        "mode",
        "run_index",
        "avg_capture_fps",
        "pipeline_hz_est",
        "p95_pipeline_ms",
        "avg_pipeline_ms",
        "detector_fps_est",
        "tracker_fps_est",
        "visual_fps_est",
        "avg_cpu_percent",
        "max_ram_gb",
        "max_gpu_ram_gb",
        "errors",
        "tracebacks",
        "exit_code",
        "timed_out",
        "success",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fields, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def write_output_stats_csv(snapshots: dict[str, dict[str, Any]], path: Path) -> None:
    fields = [
        "slug",
        "capture",
        "mode",
        "mc_emit_rate",
        "sticky_tracks_mean",
        "objects_results_items",
        "vis_frames_last",
        "has_data",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fields, delimiter=";")
        writer.writeheader()
        for slug, data in sorted(snapshots.items()):
            writer.writerow({k: data.get(k, "") for k in fields})


def _stability_table(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Capture | Mode | Run | Exit | Timeout | Tracebacks | Success |",
        "| --- | --- | ---: | ---: | --- | ---: | --- |",
    ]
    for row in sorted(rows, key=lambda r: (r.get("capture", ""), r.get("mode", ""), r.get("run_index", 0))):
        lines.append(
            f"| {row.get('capture')} | {row.get('mode')} | {row.get('run_index')} | "
            f"{row.get('exit_code', '-')} | {'да' if row.get('timed_out') else 'нет'} | "
            f"{row.get('tracebacks', 0)} | {'да' if row.get('success') else 'нет'} |"
        )
    return lines


def _timing_summary_table(
    agg: dict[tuple[str, str], dict[str, Any]],
    metric: str,
    *,
    capture_filter: str | None = None,
) -> list[str]:
    lines = [
        f"| Capture | Mode | {metric} (mean±std, n) |",
        "| --- | --- | --- |",
    ]
    keys = sorted(agg.keys())
    for capture, mode in keys:
        if capture_filter and capture != capture_filter:
            continue
        lines.append(f"| {capture} | {mode} | {_fmt_stats(agg[(capture, mode)])} |")
    return lines


def _compare_thread_process(
    agg: dict[tuple[str, str], dict[str, Any]],
    metric: str,
    capture: str,
) -> list[str]:
    thread = agg.get((capture, "thread"), {})
    process = agg.get((capture, "process"), {})
    tm = thread.get("mean")
    pm = process.get("mean")
    better = "-"
    if tm is not None and pm is not None:
        if metric in ("p95_pipeline_ms", "avg_pipeline_ms", "max_ram_gb"):
            better = "thread" if tm < pm else "process"
        else:
            better = "thread" if tm > pm else "process"
    return [
        f"### {capture}: thread vs process ({metric})",
        "",
        f"- thread mean: {_fmt(tm)}",
        f"- process mean: {_fmt(pm)}",
        f"- Δ% (process vs thread): {_delta_pct(tm, pm)}",
        f"- Лучший режим (по mean): **{better}**",
        "",
    ]


def write_plots(
    agg: dict[tuple[str, str], dict[str, Any]],
    metric: str,
    title: str,
    filename: str,
    plots_dir: Path,
) -> Path | None:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except ImportError:
        return None

    captures = sorted({c for c, _ in agg.keys()})
    if not captures:
        return None
    thread_vals = []
    process_vals = []
    for cap in captures:
        thread_vals.append(_safe_float(agg.get((cap, "thread"), {}).get("mean")) or 0.0)
        process_vals.append(_safe_float(agg.get((cap, "process"), {}).get("mean")) or 0.0)

    x = list(range(len(captures)))
    width = 0.38
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar([i - width / 2 for i in x], thread_vals, width, label="thread")
    ax.bar([i + width / 2 for i in x], process_vals, width, label="process")
    ax.set_title(title)
    ax.set_xticks(x)
    ax.set_xticklabels(captures)
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    plots_dir.mkdir(parents=True, exist_ok=True)
    out_path = plots_dir / filename
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return out_path


def render_report(out_dir: Path) -> None:
    rows = collect_run_rows(out_dir)
    snapshots = load_output_snapshots(out_dir)

    metrics = [
        "avg_capture_fps",
        "pipeline_hz_est",
        "p95_pipeline_ms",
        "avg_pipeline_ms",
        "detector_fps_est",
        "tracker_fps_est",
        "avg_cpu_percent",
        "max_ram_gb",
    ]
    agg_by_metric = {m: aggregate_by_group(rows, m) for m in metrics}

    audit_path = out_dir / "config_audit.md"
    audit_section = ""
    if audit_path.exists():
        audit_section = audit_path.read_text(encoding="utf-8")

    plots_dir = out_dir / "plots"
    plot_paths: list[Path] = []
    for metric, title, fname in [
        ("pipeline_hz_est", "Pipeline Hz (оценка)", "pipeline_hz.png"),
        ("max_ram_gb", "RAM max, ГБ", "ram_gb.png"),
        ("avg_capture_fps", "Capture FPS", "capture_fps.png"),
    ]:
        p = write_plots(agg_by_metric[metric], metric, title, fname, plots_dir)
        if p:
            plot_paths.append(p)

    lines = [
        "# Сравнение poly-videos: process vs thread",
        "",
        "## Методика",
        f"- Дата отчёта: {datetime.now().isoformat(timespec='seconds')}",
        f"- Платформа: {platform.platform()}",
        f"- Python: {sys.version.split()[0]}",
        "- 5 прогонов × 180 с на конфиг, headless (`--no-gui --autoclose`)",
        "- Env: `EVILEYE_PERF_DIAG=1`, `EVILEYE_PERF_DIAG_EVERY=30`, "
        "`EVILEYE_RESOURCE_STATS_EVERY_SEC=2`, `PYTHONUNBUFFERED=1`",
        "- Bench overlay: `controller.perf_diag=true` (временный JSON, не в git)",
        "",
        "## Сводка конфигов",
        "",
        "| Capture | Mode | Config |",
        "| --- | --- | --- |",
    ]
    for spec in COMPARE_CONFIGS:
        lines.append(f"| {spec['capture']} | {spec['mode']} | `{spec['config']}` |")

    if audit_section:
        lines.extend(["", "## Аудит параметров (config_audit.md)", "", audit_section])

    lines.extend(["", "## Стабильность прогонов", "", *_stability_table(rows)])

    for cap in ("opencv", "gst"):
        lines.extend(["", f"## Временные характеристики ({cap})", ""])
        for metric in ("avg_capture_fps", "pipeline_hz_est", "p95_pipeline_ms", "max_ram_gb"):
            sub_agg = {k: v for k, v in agg_by_metric[metric].items() if k[0] == cap}
            if sub_agg:
                lines.extend([f"### {metric}", "", *_timing_summary_table(sub_agg, metric, capture_filter=cap), ""])
        lines.extend(_compare_thread_process(agg_by_metric["pipeline_hz_est"], "pipeline_hz_est", cap))

    e2e_files = sorted(out_dir.glob("e2e_*.json"))
    if e2e_files:
        lines.extend(["", "## E2E tracker FPS (сквозная)", ""])
        lines.append("| Config file | e2e_tracker_fps | e2e_p95_ms | pending_unmatched_pct |")
        lines.append("| --- | ---: | ---: | ---: |")
        for path in e2e_files:
            data = json.loads(path.read_text(encoding="utf-8"))
            lines.append(
                f"| `{path.name}` | {data.get('e2e_tracker_fps', '-')} | "
                f"{data.get('e2e_p95_ms', '-')} | {data.get('pending_unmatched_pct', '-')} |"
            )

    if snapshots:
        lines.extend(
            [
                "",
                "## Выходные данные (snapshot)",
                "",
                "| Slug | mc_emit_rate | sticky_tracks_mean | objects | has_data |",
                "| --- | ---: | ---: | ---: | --- |",
            ]
        )
        for slug, data in sorted(snapshots.items()):
            lines.append(
                f"| {slug} | {data.get('mc_emit_rate', '-')} | {data.get('sticky_tracks_mean', '-')} | "
                f"{data.get('objects_results_items', '-')} | {data.get('has_data', '-')} |"
            )
    else:
        lines.append("Снимки не найдены. Запустите `collect_poly_mode_output_snapshot.py`.")

    lines.extend(["", "## Выводы", ""])
    for cap in ("opencv", "gst"):
        lines.extend(_compare_thread_process(agg_by_metric["pipeline_hz_est"], "pipeline_hz_est", cap))

    lines.extend(["", "## Графики", ""])
    if plot_paths:
        for p in plot_paths:
            lines.append(f"- `{p.relative_to(REPO_ROOT)}`")
    else:
        lines.append("- Графики не построены (matplotlib недоступен или нет данных).")

    lines.extend(
        [
            "",
            "## Приложение",
            f"- Каталог: `{out_dir.relative_to(REPO_ROOT)}`",
            "- Воспроизведение: `python scripts/run_poly_videos_mode_compare.py`",
            "- Snapshot: `python scripts/collect_poly_mode_output_snapshot.py`",
            "",
        ]
    )

    write_results_csv(rows, out_dir / "results.csv")
    write_output_stats_csv(snapshots, out_dir / "output_stats.csv")
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Report: {out_dir / 'report.md'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render poly-videos mode compare report.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR.relative_to(REPO_ROOT)))
    args = parser.parse_args()
    out_dir = (REPO_ROOT / args.out_dir).resolve()
    if not (out_dir / "logs").exists() and not (out_dir / "run_summary.json").exists():
        print("No benchmark data found.", file=sys.stderr)
        return 1
    render_report(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
