#!/usr/bin/env python3
"""Run poly-videos benchmark: 4 configs x 5 runs x 180s (headless)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from poly_mode_compare_lib import (
    COMPARE_CONFIGS,
    DEFAULT_OUT_DIR,
    REPO_ROOT,
    apply_env_overrides,
    build_manifest,
    write_bench_config,
)

# Reuse resource sampling from multiprocessing benchmark runner.
from run_multiprocessing_benchmark import (  # noqa: E402
    _gpu_stats,
    _process_tree_stats,
    _sample_resources,
    _terminate_process_tree,
)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_process(
    *,
    config_path: Path,
    log_path: Path,
    sample_path: Path,
    timeout_sec: int,
    sample_interval_sec: float,
    perf_every: int,
    python_executable: str,
    meta: dict[str, Any],
) -> dict[str, Any]:
    cmd = [
        python_executable,
        "-m",
        "evileye.process",
        "--config",
        str(config_path),
        "--no-gui",
        "--autoclose",
        "--log-level",
        "INFO",
    ]
    env = apply_env_overrides(os.environ.copy())
    env["EVILEYE_PERF_DIAG"] = "1"
    env["EVILEYE_PERF_DIAG_EVERY"] = str(perf_every)
    env["EVILEYE_PIPELINE_TIMELINE"] = "0"
    env.setdefault("EVILEYE_RESOURCE_STATS_EVERY_SEC", str(max(1, int(sample_interval_sec))))
    env["PYTHONUNBUFFERED"] = "1"

    log_path.parent.mkdir(parents=True, exist_ok=True)
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    timed_out = False

    with log_path.open("w", encoding="utf-8", newline="") as log:
        for key, value in meta.items():
            log.write(f"# {key}: {value}\n")
        log.write(f"# command: {' '.join(cmd)}\n")
        log.write(f"# started_at: {datetime.now().isoformat(timespec='seconds')}\n")
        log.flush()

        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        stop_event = threading.Event()
        sampler = threading.Thread(
            target=_sample_resources,
            args=(proc, sample_path, stop_event, sample_interval_sec),
            daemon=True,
        )
        sampler.start()
        try:
            exit_code = proc.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            timed_out = True
            log.write(f"\n# timeout after {timeout_sec}s\n")
            log.flush()
            _terminate_process_tree(proc)
            exit_code = 124
        finally:
            stop_event.set()
            sampler.join(timeout=3)
            elapsed = time.time() - started
            log.write(f"\n# elapsed_sec: {elapsed:.3f}\n")
            log.write(f"# exit_code: {exit_code}\n")

    return {
        **meta,
        "config": str(config_path),
        "log": str(log_path.relative_to(REPO_ROOT)),
        "samples": str(sample_path.relative_to(REPO_ROOT)),
        "exit_code": int(exit_code),
        "timed_out": timed_out,
        "elapsed_sec": round(time.time() - started, 3),
    }


def _run_one_slot(
    spec: dict[str, str],
    *,
    run_index: int | None,
    kind: str,
    out_dir: Path,
    timeout_sec: int,
    sample_interval_sec: float,
    perf_every: int,
    python_executable: str,
) -> dict[str, Any]:
    slug = spec["slug"]
    if kind == "warmup":
        log_name = f"warmup_{slug}.log"
        sample_name = f"warmup_{slug}.csv"
        run_index_meta = "warmup"
    else:
        idx = int(run_index or 0)
        log_name = f"{slug}_run{idx:02d}.log"
        sample_name = f"{slug}_run{idx:02d}.csv"
        run_index_meta = idx

    base_config = REPO_ROOT / spec["config"]
    overlay = write_bench_config(base_config)
    try:
        meta = {
            "slug": slug,
            "capture": spec["capture"],
            "mode": spec["mode"],
            "base_config": spec["config"],
            "run_index": run_index_meta,
            "kind": kind,
        }
        result = _run_process(
            config_path=overlay,
            log_path=out_dir / "logs" / log_name,
            sample_path=out_dir / "samples" / sample_name,
            timeout_sec=timeout_sec,
            sample_interval_sec=sample_interval_sec,
            perf_every=perf_every,
            python_executable=python_executable,
            meta=meta,
        )
        text = (out_dir / "logs" / log_name).read_text(encoding="utf-8", errors="ignore")
        result["tracebacks"] = text.count("Traceback (most recent call last):")
        result["errors"] = len(__import__("re").findall(r"\bERROR\b", text))
        # 180s runs end with timeout (exit 124) by design.
        result["success"] = (
            result["exit_code"] in (0, 124)
            and result["tracebacks"] == 0
            and result.get("errors", 0) < 50
        )
        return result
    finally:
        try:
            overlay.unlink(missing_ok=True)
        except OSError:
            pass


def _merge_runs(existing: list[dict[str, Any]], new_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, int], dict[str, Any]] = {}
    for run in existing:
        slug = str(run.get("slug", ""))
        try:
            idx = int(run.get("run_index", 0))
        except (TypeError, ValueError):
            continue
        if slug and idx:
            by_key[(slug, idx)] = run
    for run in new_runs:
        slug = str(run.get("slug", ""))
        try:
            idx = int(run.get("run_index", 0))
        except (TypeError, ValueError):
            continue
        if slug and idx:
            by_key[(slug, idx)] = run
    return sorted(by_key.values(), key=lambda r: (str(r.get("slug")), int(r.get("run_index", 0))))


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = (REPO_ROOT / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(runs_per_config=args.runs_per_config)
    _write_json(out_dir / "manifest.json", manifest)

    prev_summary: dict[str, Any] = {}
    summary_path = out_dir / "run_summary.json"
    if summary_path.exists() and (args.only_failed or args.rerun_from_summary):
        prev_summary = json.loads(summary_path.read_text(encoding="utf-8"))

    summary: dict[str, Any] = {
        "started_at": prev_summary.get("started_at")
        or datetime.now().isoformat(timespec="seconds"),
        "timeout_sec": args.timeout_sec,
        "runs_per_config": args.runs_per_config,
        "warmups": list(prev_summary.get("warmups") or []),
        "runs": list(prev_summary.get("runs") or []) if args.only_failed else [],
    }

    specs = COMPARE_CONFIGS
    if args.configs:
        wanted = set(args.configs)
        specs = [s for s in specs if s["slug"] in wanted or s["config"] in wanted]

    if not args.skip_warmup:
        for spec in specs:
            print(f"Warmup: {spec['slug']} ({args.warmup_sec}s)")
            summary["warmups"].append(
                _run_one_slot(
                    spec,
                    run_index=None,
                    kind="warmup",
                    out_dir=out_dir,
                    timeout_sec=args.warmup_sec,
                    sample_interval_sec=args.sample_interval_sec,
                    perf_every=args.perf_every,
                    python_executable=args.python,
                )
            )

    for spec in specs:
        for run_index in range(1, args.runs_per_config + 1):
            if args.only_failed:
                continue
            if args.run_indices and run_index not in args.run_indices:
                continue
            print(f"Run: {spec['slug']} #{run_index} ({args.timeout_sec}s)")
            summary["runs"].append(
                _run_one_slot(
                    spec,
                    run_index=run_index,
                    kind="run",
                    out_dir=out_dir,
                    timeout_sec=args.timeout_sec,
                    sample_interval_sec=args.sample_interval_sec,
                    perf_every=args.perf_every,
                    python_executable=args.python,
                )
            )

    new_runs: list[dict[str, Any]] = []
    if args.only_failed and args.rerun_from_summary:
        prev_runs = prev_summary.get("runs") or summary.get("runs") or []
        for prev_run in prev_runs:
            if prev_run.get("success"):
                continue
            slug = prev_run.get("slug")
            if args.configs and slug not in args.configs:
                continue
            spec = next((s for s in COMPARE_CONFIGS if s["slug"] == slug), None)
            if spec is None:
                continue
            idx = int(prev_run.get("run_index", 0))
            print(f"Re-run failed: {slug} #{idx}")
            new_runs.append(
                _run_one_slot(
                    spec,
                    run_index=idx,
                    kind="run",
                    out_dir=out_dir,
                    timeout_sec=args.timeout_sec,
                    sample_interval_sec=args.sample_interval_sec,
                    perf_every=args.perf_every,
                    python_executable=args.python,
                )
            )

    if new_runs:
        summary["runs"] = _merge_runs(summary.get("runs") or [], new_runs)
    elif not args.only_failed:
        pass  # runs already in summary["runs"] from main loop

    summary["finished_at"] = datetime.now().isoformat(timespec="seconds")
    _write_json(out_dir / "run_summary.json", summary)
    failed = [r for r in summary["runs"] if not r.get("success")]
    print(f"Done. runs={len(summary['runs'])} failed={len(failed)}")
    print(f"Summary: {out_dir / 'run_summary.json'}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Poly-videos process vs thread benchmark runner.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR.relative_to(REPO_ROOT)))
    parser.add_argument("--timeout-sec", type=int, default=180)
    parser.add_argument("--warmup-sec", type=int, default=60)
    parser.add_argument("--runs-per-config", type=int, default=5)
    parser.add_argument("--sample-interval-sec", type=float, default=2.0)
    parser.add_argument("--perf-every", type=int, default=30)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--configs", nargs="*", help="slug or config path filter")
    parser.add_argument("--run-indices", type=int, nargs="*")
    parser.add_argument("--skip-warmup", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="30s smoke per config only")
    parser.add_argument("--only-failed", action="store_true")
    parser.add_argument("--rerun-from-summary", action="store_true")
    args = parser.parse_args()

    if args.smoke:
        args.timeout_sec = 30
        args.runs_per_config = 1
        args.skip_warmup = True
        args.warmup_sec = 0

    summary = run_benchmark(args)
    failed = [r for r in summary.get("runs", []) if not r.get("success")]
    return 1 if failed and not args.smoke else 0


if __name__ == "__main__":
    raise SystemExit(main())
