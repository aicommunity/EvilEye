#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_MANIFEST = "reports/bench_multiprocessing/configs/manifest.json"
DEFAULT_OUT_DIR = "reports/bench_multiprocessing"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _gpu_stats() -> tuple[float | None, float | None]:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return None, None
    try:
        proc = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None, None
    if proc.returncode != 0:
        return None, None

    mem_total = 0.0
    util_values: list[float] = []
    for line in proc.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            mem_total += float(parts[0])
            util_values.append(float(parts[1]))
        except ValueError:
            continue
    util_avg = sum(util_values) / len(util_values) if util_values else None
    return mem_total if mem_total > 0 else None, util_avg


def _process_tree_stats(pid: int) -> tuple[float | None, float | None, int | None, int | None]:
    try:
        import psutil  # type: ignore
    except ImportError:
        return None, None, None, None

    try:
        root = psutil.Process(pid)
        processes = [root, *root.children(recursive=True)]
    except (psutil.Error, OSError):
        return None, None, None, None

    cpu_total = 0.0
    rss_total = 0.0
    threads_total = 0
    alive = 0
    for proc in processes:
        try:
            cpu_total += float(proc.cpu_percent(interval=0.01))
            rss_total += float(proc.memory_info().rss) / (1024 * 1024)
            threads_total += int(proc.num_threads())
            alive += 1
        except (psutil.Error, OSError):
            continue
    return cpu_total, rss_total, threads_total, alive


def _terminate_process_tree(proc: subprocess.Popen[Any]) -> bool:
    try:
        import psutil  # type: ignore
    except ImportError:
        try:
            proc.terminate()
            return True
        except (OSError, PermissionError):
            return False

    try:
        parent = psutil.Process(proc.pid)
        children = parent.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except (psutil.Error, OSError):
                pass
        parent.terminate()
        _gone, alive = psutil.wait_procs([parent, *children], timeout=5)
        for item in alive:
            try:
                item.kill()
            except (psutil.Error, OSError):
                pass
        return True
    except (psutil.Error, OSError):
        try:
            proc.kill()
            return True
        except (OSError, PermissionError):
            return False


def _sample_resources(
    proc: subprocess.Popen[Any],
    sample_path: Path,
    stop_event: threading.Event,
    interval_sec: float,
) -> None:
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    with sample_path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(
            out,
            fieldnames=[
                "timestamp",
                "elapsed_sec",
                "cpu_percent",
                "rss_mb",
                "threads",
                "processes",
                "gpu_ram_mb",
                "gpu_util_percent",
            ],
        )
        writer.writeheader()
        started = time.time()
        while not stop_event.wait(max(0.1, interval_sec)):
            if proc.poll() is not None:
                break
            cpu, rss, threads, processes = _process_tree_stats(proc.pid)
            gpu_ram, gpu_util = _gpu_stats()
            writer.writerow(
                {
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "elapsed_sec": f"{time.time() - started:.3f}",
                    "cpu_percent": "" if cpu is None else f"{cpu:.3f}",
                    "rss_mb": "" if rss is None else f"{rss:.3f}",
                    "threads": "" if threads is None else str(threads),
                    "processes": "" if processes is None else str(processes),
                    "gpu_ram_mb": "" if gpu_ram is None else f"{gpu_ram:.3f}",
                    "gpu_util_percent": "" if gpu_util is None else f"{gpu_util:.3f}",
                }
            )
            out.flush()


def _run_one(
    run: dict[str, Any],
    *,
    repo_root: Path,
    logs_dir: Path,
    samples_dir: Path,
    timeout_sec: int,
    duration_sec: int | None,
    sample_interval_sec: float,
    perf_every: int,
    python_executable: str,
    autoclose: bool,
    duration_hard_stop: bool,
    duration_stop_grace_sec: int,
) -> dict[str, Any]:
    camera_count = int(run["camera_count"])
    mode = str(run["mode"])
    config_path = repo_root / str(run["config"])
    stem = f"{camera_count:02d}cam_{mode}"
    log_path = logs_dir / f"{stem}.log"
    sample_path = samples_dir / f"{stem}.csv"

    cmd = [
        python_executable,
        "-m",
        "evileye.process",
        "--config",
        str(config_path),
        "--no-gui",
        "--autoclose" if autoclose else "--no-autoclose",
        "--log-level",
        "INFO",
    ]
    env = os.environ.copy()
    env["EVILEYE_PERF_DIAG"] = "1"
    env["EVILEYE_PERF_DIAG_EVERY"] = str(perf_every)
    if duration_sec is not None:
        env["EVILEYE_BENCHMARK_DURATION_SEC"] = str(duration_sec)
    env.setdefault("EVILEYE_RESOURCE_STATS_EVERY_SEC", str(max(1, int(sample_interval_sec))))
    env.setdefault("PYTHONUNBUFFERED", "1")

    logs_dir.mkdir(parents=True, exist_ok=True)
    samples_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    timed_out = False
    terminate_ok = True
    stopped_by_duration = False

    with log_path.open("w", encoding="utf-8", newline="") as log:
        log.write(f"# command: {' '.join(cmd)}\n")
        log.write(f"# started_at: {datetime.now().isoformat(timespec='seconds')}\n")
        log.write(f"# camera_count: {camera_count}\n")
        log.write(f"# mode: {mode}\n")
        log.flush()

        proc = subprocess.Popen(
            cmd,
            cwd=str(repo_root),
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

        wait_limit = timeout_sec
        if duration_sec is not None:
            wait_limit = (
                duration_sec + max(1, duration_stop_grace_sec)
                if duration_hard_stop
                else max(timeout_sec, duration_sec + 120)
            )
        try:
            exit_code = proc.wait(timeout=wait_limit)
        except subprocess.TimeoutExpired:
            if duration_sec is not None and duration_hard_stop:
                log.write(f"\n# hard_stopped_by_duration after {duration_sec}s + {duration_stop_grace_sec}s grace\n")
                log.flush()
                terminate_ok = _terminate_process_tree(proc)
                if not terminate_ok:
                    log.write("# terminate_failed: could not stop process tree after duration\n")
                    log.flush()
                stopped_by_duration = True
                timed_out = not terminate_ok
                exit_code = 0 if terminate_ok else 124
            elif duration_sec is not None:
                timed_out = True
                log.write(f"\n# stopped_by_duration after {duration_sec}s\n")
                log.flush()
                terminate_ok = _terminate_process_tree(proc)
                if not terminate_ok:
                    log.write("# terminate_failed: could not stop process tree after duration\n")
                    log.flush()
                exit_code = 124
            else:
                timed_out = True
                log.write(f"\n# timeout after {timeout_sec}s\n")
                log.flush()
                terminate_ok = _terminate_process_tree(proc)
                if not terminate_ok:
                    log.write("# terminate_failed: could not stop process tree after timeout\n")
                    log.flush()
                exit_code = 124
        finally:
            stop_event.set()
            sampler.join(timeout=3)
            elapsed = time.time() - started
            log.write(f"\n# elapsed_sec: {elapsed:.3f}\n")

    return {
        "camera_count": camera_count,
        "mode": mode,
        "config": str(config_path.relative_to(repo_root)),
        "log": str(log_path.relative_to(repo_root)),
        "samples": str(sample_path.relative_to(repo_root)),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stopped_by_duration": stopped_by_duration or (duration_sec is not None and exit_code == 0),
        "terminate_ok": terminate_ok,
        "elapsed_sec": round(time.time() - started, 3),
    }


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = _repo_root()
    manifest_path = (repo_root / args.manifest).resolve()
    manifest = _load_json(manifest_path)
    out_dir = (repo_root / args.out_dir).resolve()
    logs_dir = out_dir / "logs"
    samples_dir = out_dir / "samples"

    runs = manifest.get("runs", [])
    if args.camera_counts:
        wanted = {int(item) for item in args.camera_counts}
        runs = [run for run in runs if int(run.get("camera_count", 0)) in wanted]
    if args.modes:
        wanted_modes = set(args.modes)
        runs = [run for run in runs if str(run.get("mode")) in wanted_modes]
    if not runs:
        raise SystemExit("В manifest не найдено запусков для выбранных фильтров.")

    started_at = datetime.now().isoformat(timespec="seconds")
    summary = {
        "started_at": started_at,
        "manifest": str(manifest_path.relative_to(repo_root)),
        "timeout_sec": args.timeout_sec,
        "duration_sec": args.duration_sec,
        "autoclose": args.autoclose,
        "sample_interval_sec": args.sample_interval_sec,
        "runs": [],
    }
    for run in runs:
        print(f"Запуск: {run['camera_count']} камер, режим {run['mode']}")
        summary["runs"].append(
            _run_one(
                run,
                repo_root=repo_root,
                logs_dir=logs_dir,
                samples_dir=samples_dir,
                timeout_sec=args.timeout_sec,
                duration_sec=args.duration_sec,
                sample_interval_sec=args.sample_interval_sec,
                perf_every=args.perf_every,
                python_executable=args.python,
                autoclose=args.autoclose,
                duration_hard_stop=args.duration_hard_stop,
                duration_stop_grace_sec=args.duration_stop_grace_sec,
            )
        )

    summary["finished_at"] = datetime.now().isoformat(timespec="seconds")
    summary_path = out_dir / "run_summary.json"
    _write_json(summary_path, summary)
    print(f"Сводка запусков сохранена: {summary_path.relative_to(repo_root)}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Запустить подготовленные benchmark-конфиги EvilEye и собрать логи/ресурсы."
    )
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--timeout-sec", type=int, default=180)
    parser.add_argument(
        "--duration-sec",
        type=int,
        default=None,
        help="Фиксированная длительность измерения. По истечении процесс останавливается штатно и не считается timeout.",
    )
    parser.add_argument("--sample-interval-sec", type=float, default=2.0)
    parser.add_argument("--perf-every", type=int, default=30)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--duration-hard-stop",
        action="store_true",
        help=(
            "Для fixed-duration benchmark завершать дерево процессов после "
            "--duration-sec + --duration-stop-grace-sec и считать прогон остановленным по длительности, "
            "если завершение прошло успешно."
        ),
    )
    parser.add_argument("--duration-stop-grace-sec", type=int, default=30)
    parser.add_argument("--camera-counts", type=int, nargs="*")
    parser.add_argument("--modes", choices=["thread", "process"], nargs="*")
    parser.add_argument(
        "--autoclose",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Передавать ли --autoclose в evileye.process. Для duration benchmark используйте --no-autoclose.",
    )
    args = parser.parse_args()

    run_benchmark(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
