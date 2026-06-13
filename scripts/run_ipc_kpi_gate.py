#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from benchmark_ipc_kpi import parse_log


def _load_profile(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _run_config(config_path: str, timeout_sec: int, log_path: Path) -> tuple[int, bool]:
    cmd = [
        sys.executable,
        "-m",
        "evileye.process",
        "--config",
        config_path,
        "--no-gui",
        "--autoclose",
    ]
    env = os.environ.copy()
    env.setdefault("EVILEYE_PERF_DIAG", "1")
    env.setdefault("EVILEYE_PERF_DIAG_EVERY", "30")

    start = time.time()
    timed_out = False
    with log_path.open("w", encoding="utf-8") as out:
        out.write(f"# command: {' '.join(cmd)}\n")
        out.write(f"# started_at: {datetime.now().isoformat()}\n")
        out.flush()
        try:
            proc = subprocess.run(
                cmd,
                stdout=out,
                stderr=subprocess.STDOUT,
                env=env,
                timeout=timeout_sec,
                cwd=str(Path(__file__).resolve().parents[1]),
                check=False,
            )
            return proc.returncode, timed_out
        except subprocess.TimeoutExpired:
            timed_out = True
            out.write(f"\n# timeout after {timeout_sec}s\n")
            out.flush()
            return 124, timed_out
        finally:
            elapsed = time.time() - start
            out.write(f"\n# elapsed_sec: {elapsed:.3f}\n")


def _evaluate_metrics(metrics: dict[str, Any], args: argparse.Namespace) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if metrics.get("errors", 0) > args.max_errors:
        reasons.append(f"errors={metrics.get('errors', 0)} > {args.max_errors}")
    if metrics.get("tracebacks", 0) > args.max_tracebacks:
        reasons.append(f"tracebacks={metrics.get('tracebacks', 0)} > {args.max_tracebacks}")
    if metrics.get("stop_timeouts", 0) > args.max_stop_timeouts:
        reasons.append(f"stop_timeouts={metrics.get('stop_timeouts', 0)} > {args.max_stop_timeouts}")
    if metrics.get("force_kills", 0) > args.max_force_kills:
        reasons.append(f"force_kills={metrics.get('force_kills', 0)} > {args.max_force_kills}")
    if metrics.get("restart_events", 0) > args.max_restarts:
        reasons.append(f"restart_events={metrics.get('restart_events', 0)} > {args.max_restarts}")
    if float(metrics.get("p95_pipeline_ms", 0.0)) > args.max_p95_pipeline_ms:
        reasons.append(
            f"p95_pipeline_ms={metrics.get('p95_pipeline_ms', 0.0):.3f} > {args.max_p95_pipeline_ms:.3f}"
        )
    if float(metrics.get("max_rss_mb", 0.0)) > args.max_rss_mb:
        reasons.append(f"max_rss_mb={metrics.get('max_rss_mb', 0.0):.3f} > {args.max_rss_mb:.3f}")
    if int(metrics.get("pipeline_samples", 0)) < args.min_pipeline_samples:
        reasons.append(f"pipeline_samples={metrics.get('pipeline_samples', 0)} < {args.min_pipeline_samples}")
    return len(reasons) == 0, reasons


def _render_report(
    rows: list[dict[str, Any]], thresholds: dict[str, Any], out_dir: Path, started_at: str
) -> str:
    lines = [
        "# IPC KPI Gate Report",
        "",
        f"- Started at: `{started_at}`",
        f"- Reports dir: `{out_dir}`",
        "",
        "## Thresholds",
    ]
    for key, value in thresholds.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "## Results",
            "",
            "| Config | Exit | Timeout | Warnings | Errors | Tracebacks | Restarts | Stop timeouts | Force-kills | p95 ms | Est. Hz | Avg FPS | Max RSS MB | Pipeline samples | Gate |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in rows:
        m = row["metrics"]
        lines.append(
            "| {config} | {exit_code} | {timed_out} | {warnings} | {errors} | {tracebacks} | {restart_events} | "
            "{stop_timeouts} | {force_kills} | {p95:.3f} | {hz:.3f} | {fps:.3f} | {rss:.3f} | {samples} | {gate} |".format(
                config=row["config"],
                exit_code=row["exit_code"],
                timed_out="yes" if row["timed_out"] else "no",
                warnings=m.get("warnings", 0),
                errors=m.get("errors", 0),
                tracebacks=m.get("tracebacks", 0),
                restart_events=m.get("restart_events", 0),
                stop_timeouts=m.get("stop_timeouts", 0),
                force_kills=m.get("force_kills", 0),
                p95=float(m.get("p95_pipeline_ms", 0.0)),
                hz=float(m.get("pipeline_hz_est", 0.0)),
                fps=float(m.get("avg_capture_fps", 0.0)),
                rss=float(m.get("max_rss_mb", 0.0)),
                samples=int(m.get("pipeline_samples", 0)),
                gate="PASS" if row["gate_ok"] else "FAIL",
            )
        )
    all_ok = all(r["gate_ok"] and (r["exit_code"] in (0, 124)) for r in rows)
    lines.extend(
        [
            "",
            "## Gate Verdict",
            f"- Status: {'PASS' if all_ok else 'FAIL'}",
            "",
        ]
    )
    for row in rows:
        if row["gate_ok"]:
            continue
        lines.append(f"- `{row['config']}` failed:")
        for reason in row["reasons"]:
            lines.append(f"  - {reason}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run target configs and enforce IPC KPI gate.")
    parser.add_argument(
        "--configs",
        nargs="+",
        default=[
            "configs/single_video_multiprocess.json",
            "configs/poly-videos-gst.json",
        ],
        help="List of config paths to run.",
    )
    parser.add_argument("--timeout-sec", type=int, default=90)
    parser.add_argument("--out-dir", default="reports")
    parser.add_argument("--profile", default="configs/kpi_gate_profile.json")
    parser.add_argument("--max-errors", type=int, default=0)
    parser.add_argument("--max-tracebacks", type=int, default=0)
    parser.add_argument("--max-stop-timeouts", type=int, default=0)
    parser.add_argument("--max-force-kills", type=int, default=0)
    parser.add_argument("--max-restarts", type=int, default=20)
    parser.add_argument("--max-p95-pipeline-ms", type=float, default=200.0)
    parser.add_argument("--max-rss-mb", type=float, default=4096.0)
    parser.add_argument("--min-pipeline-samples", type=int, default=1)
    args = parser.parse_args()
    profile = _load_profile(args.profile)

    if isinstance(profile.get("configs"), list) and profile.get("configs"):
        args.configs = profile["configs"]
    thresholds = profile.get("thresholds") if isinstance(profile.get("thresholds"), dict) else {}
    for key in (
        "max_errors",
        "max_tracebacks",
        "max_stop_timeouts",
        "max_force_kills",
        "max_restarts",
        "max_p95_pipeline_ms",
        "max_rss_mb",
        "min_pipeline_samples",
        "timeout_sec",
    ):
        if key in thresholds and hasattr(args, key):
            setattr(args, key, thresholds[key])

    started_at = datetime.now().isoformat(timespec="seconds")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_dir = out_dir / f"ipc_kpi_gate_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for config in args.configs:
        cfg_name = Path(config).stem
        log_path = run_dir / f"{cfg_name}.log"
        exit_code, timed_out = _run_config(config, args.timeout_sec, log_path)
        metrics = parse_log(log_path)
        gate_ok, reasons = _evaluate_metrics(metrics, args)
        rows.append(
            {
                "config": config,
                "log_path": str(log_path),
                "exit_code": exit_code,
                "timed_out": timed_out,
                "metrics": metrics,
                "gate_ok": gate_ok,
                "reasons": reasons,
            }
        )

    applied_thresholds = {
        "max_errors": args.max_errors,
        "max_tracebacks": args.max_tracebacks,
        "max_stop_timeouts": args.max_stop_timeouts,
        "max_force_kills": args.max_force_kills,
        "max_restarts": args.max_restarts,
        "max_p95_pipeline_ms": args.max_p95_pipeline_ms,
        "max_rss_mb": args.max_rss_mb,
        "min_pipeline_samples": args.min_pipeline_samples,
        "timeout_sec": args.timeout_sec,
    }
    report_text = _render_report(rows, applied_thresholds, run_dir, started_at)
    report_path = run_dir / "report.md"
    report_path.write_text(report_text + "\n", encoding="utf-8")

    summary_path = run_dir / "summary.json"
    summary_path.write_text(
        json.dumps(
            {"rows": rows, "thresholds": applied_thresholds, "profile": args.profile},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Report: {report_path}")
    print(f"Summary: {summary_path}")
    all_ok = all(r["gate_ok"] and (r["exit_code"] in (0, 124)) for r in rows)
    return 0 if all_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
