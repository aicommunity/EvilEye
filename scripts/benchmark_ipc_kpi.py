#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


def _count(pattern: str, text: str) -> int:
    return len(re.findall(pattern, text, flags=re.MULTILINE))


def parse_log(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    pipeline_totals = [float(x) for x in re.findall(r"PerfDiag\(Pipeline\):.*?total=([0-9.]+)ms", text)]
    rss_values = [float(x) for x in re.findall(r"'total_memory_usage_mb':\s*([0-9.]+)", text)]
    p95_pipeline_ms = 0.0
    pipeline_hz = 0.0
    capture_fps_values = [float(x) for x in re.findall(r"\bFPS=([0-9.]+)\b", text)]
    avg_capture_fps = (sum(capture_fps_values) / len(capture_fps_values)) if capture_fps_values else 0.0
    if pipeline_totals:
        sorted_vals = sorted(pipeline_totals)
        idx = max(0, int(0.95 * (len(sorted_vals) - 1)))
        p95_pipeline_ms = sorted_vals[idx]
        if p95_pipeline_ms > 0:
            pipeline_hz = 1000.0 / p95_pipeline_ms
    return {
        "path": str(path),
        "warnings": _count(r"\bWARNING\b", text),
        "errors": _count(r"\bERROR\b", text),
        "tracebacks": _count(r"Traceback \(most recent call last\):", text),
        "restart_events": _count(r"restarting", text),
        "restart_suppressed": _count(r"restart suppressed by policy", text),
        "stop_timeouts": _count(r"stop timeout", text),
        "force_kills": _count(r"Force-killing worker", text),
        "p95_pipeline_ms": p95_pipeline_ms,
        "pipeline_hz_est": pipeline_hz,
        "pipeline_samples": len(pipeline_totals),
        "avg_capture_fps": avg_capture_fps,
        "capture_fps_samples": len(capture_fps_values),
        "max_rss_mb": max(rss_values) if rss_values else 0.0,
    }


def render_report(baseline: dict, candidate: dict) -> str:
    keys = [
        ("warnings", "Warnings"),
        ("errors", "Errors"),
        ("tracebacks", "Tracebacks"),
        ("restart_events", "Worker restarts"),
        ("restart_suppressed", "Suppressed restarts"),
        ("stop_timeouts", "Stop timeouts"),
        ("force_kills", "Force-kills"),
    ]
    float_keys = [
        ("p95_pipeline_ms", "p95 Pipeline loop (ms)"),
        ("pipeline_hz_est", "Estimated pipeline Hz"),
        ("avg_capture_fps", "Average capture FPS"),
        ("max_rss_mb", "Max RSS (MB)"),
    ]
    lines = [
        "# IPC KPI Comparison",
        "",
        f"- Baseline log: `{baseline['path']}`",
        f"- Candidate log: `{candidate['path']}`",
        "",
        "| KPI | Baseline | Candidate | Delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for key, title in keys:
        b = int(baseline.get(key, 0))
        c = int(candidate.get(key, 0))
        delta = c - b
        lines.append(f"| {title} | {b} | {c} | {delta:+d} |")
    for key, title in float_keys:
        b = float(baseline.get(key, 0.0))
        c = float(candidate.get(key, 0.0))
        delta = c - b
        lines.append(f"| {title} | {b:.3f} | {c:.3f} | {delta:+.3f} |")
    lines.extend(
        [
            "",
            "## Notes",
            "- Lower is better for `Errors`, `Tracebacks`, `Worker restarts`, `Stop timeouts`, `Force-kills`.",
            "- `Suppressed restarts` indicates graceful policy behavior and is informational.",
            "",
        ]
    )
    return "\n".join(lines)


def evaluate_gate(candidate: dict, args: argparse.Namespace) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if candidate.get("errors", 0) > args.max_errors:
        reasons.append(f"errors={candidate.get('errors', 0)} > {args.max_errors}")
    if candidate.get("tracebacks", 0) > args.max_tracebacks:
        reasons.append(f"tracebacks={candidate.get('tracebacks', 0)} > {args.max_tracebacks}")
    if candidate.get("stop_timeouts", 0) > args.max_stop_timeouts:
        reasons.append(f"stop_timeouts={candidate.get('stop_timeouts', 0)} > {args.max_stop_timeouts}")
    if candidate.get("force_kills", 0) > args.max_force_kills:
        reasons.append(f"force_kills={candidate.get('force_kills', 0)} > {args.max_force_kills}")
    if candidate.get("restart_events", 0) > args.max_restarts:
        reasons.append(f"restart_events={candidate.get('restart_events', 0)} > {args.max_restarts}")
    if float(candidate.get("p95_pipeline_ms", 0.0)) > args.max_p95_pipeline_ms:
        reasons.append(
            f"p95_pipeline_ms={candidate.get('p95_pipeline_ms', 0.0):.3f} > {args.max_p95_pipeline_ms:.3f}"
        )
    if float(candidate.get("max_rss_mb", 0.0)) > args.max_rss_mb:
        reasons.append(f"max_rss_mb={candidate.get('max_rss_mb', 0.0):.3f} > {args.max_rss_mb:.3f}")
    if int(candidate.get("pipeline_samples", 0)) < args.min_pipeline_samples:
        reasons.append(
            f"pipeline_samples={candidate.get('pipeline_samples', 0)} < {args.min_pipeline_samples}"
        )
    return (len(reasons) == 0), reasons


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare IPC KPIs from two run logs.")
    parser.add_argument("--baseline-log", required=True)
    parser.add_argument("--candidate-log", required=True)
    parser.add_argument("--out", required=True, help="Output markdown report path.")
    parser.add_argument("--max-errors", type=int, default=0)
    parser.add_argument("--max-tracebacks", type=int, default=0)
    parser.add_argument("--max-stop-timeouts", type=int, default=0)
    parser.add_argument("--max-force-kills", type=int, default=0)
    parser.add_argument("--max-restarts", type=int, default=20)
    parser.add_argument("--max-p95-pipeline-ms", type=float, default=200.0)
    parser.add_argument("--max-rss-mb", type=float, default=4096.0)
    parser.add_argument("--min-pipeline-samples", type=int, default=1)
    args = parser.parse_args()

    baseline = parse_log(Path(args.baseline_log))
    candidate = parse_log(Path(args.candidate_log))
    report = render_report(baseline, candidate)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    gate_ok, reasons = evaluate_gate(candidate, args)
    gate_lines = [
        "## KPI Gate",
        f"- Status: {'PASS' if gate_ok else 'FAIL'}",
    ]
    if reasons:
        gate_lines.append("- Reasons:")
        for reason in reasons:
            gate_lines.append(f"  - {reason}")
    out.write_text(report + "\n" + "\n".join(gate_lines) + "\n", encoding="utf-8")
    print(f"Report written: {out}")
    if not gate_ok:
        print("KPI gate failed")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
