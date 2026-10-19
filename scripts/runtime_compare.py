#!/usr/bin/env python3
"""Compare end-to-end throughput of two EvilEye checkouts on the same clip and config.

Both trees process the same video clip with the same detector/tracker settings and exit at
end of file (``--autoclose``). Wall time is measured from the "Pipeline started" log line to
process exit, so model loading is excluded; frames / seconds is the throughput. The branch
also publishes runtime telemetry, polled through the control socket, to report queue drops.

    python scripts/runtime_compare.py --video v.mp4 --seconds 60 --runs 3 \
        --tree main=/tmp/eye_main --tree branch=$HOME/EvilEye

Linux only. Models are taken from ``<tree>/models`` (symlink it for a worktree).
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CONFIG_NAME = "_runtime_compare.json"
STARTED = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+).*Pipeline started")
PERF = re.compile(r"PerfDiag\((DetectorsIn|TrackersOut)\): window=\d+ updates=(\{[^}]*\})")


def make_clip(video: str, seconds: int, workdir: Path) -> Path:
    clip = workdir / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-ss", "0", "-t", str(seconds), "-i", video, "-an", "-c:v", "copy", str(clip)],
        check=True,
    )
    return clip


def frame_count(clip: Path) -> int:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(clip)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return int(out)


def build_config(tree: Path, clip: Path, model: str, tracker: bool, queue_size: int | None = None,
                 execution_mode: str | None = None) -> dict:
    base = json.loads((tree / "configs" / "hardhat_1cam.json").read_text(encoding="utf-8"))
    cfg = copy.deepcopy(base)
    source = cfg["pipeline"]["sources"][0]
    source.update({"camera": str(clip), "source_names": ["Clip"], "source_ids": [0], "loop_play": False})
    detector = cfg["pipeline"]["detectors"][0]
    detector.update({"type": "ObjectDetectorYolo", "model": model, "classes": [0], "source_ids": [0],
                     "inference_size": 640, "conf": 0.25, "vid_stride": 1, "roi": [[]], "num_detection_threads": 1})
    cfg["pipeline"]["trackers"] = base["pipeline"]["trackers"][:1] if tracker else []
    cfg["pipeline"]["mc_trackers"] = []
    if queue_size:
        for stage in ("detectors", "trackers"):
            for item in cfg["pipeline"].get(stage, []):
                item["queue_size"] = queue_size
    if execution_mode:
        for stage in ("detectors", "trackers"):
            for item in cfg["pipeline"].get(stage, []):
                item["execution_mode"] = execution_mode
    cfg["events_detectors"] = {}
    cfg["controller"].update({"gui_enabled": False, "show_main_gui": False, "autoclose": True, "auto_restart": False})
    cfg["record"].update({"enabled": False, "continuous_recording_enabled": False})
    cfg["storage_monitor"]["enabled"] = False
    cfg["server"]["enabled"] = False
    cfg["visualizer"].update({"source_ids": [0], "fps": [30]})
    return cfg


def poll(runtime: Path) -> dict | None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ["XDG_RUNTIME_DIR"] = str(runtime)
    try:
        from evileye.api.core.control_ipc import send_control_command

        reply = send_control_command({"cmd": "get_runtime_stats"}, timeout=2.0)
    except Exception:
        return None
    if not isinstance(reply, dict) or not reply.get("ok"):
        return None
    modules = ((reply.get("stats") or {}).get("components") or {}).get("pipeline", {}).get("module_instances") or {}
    drops = {name: m.get("input_queue_dropped", 0) for name, m in modules.items() if "input_queue_dropped" in m}
    return {"drops": drops, "item_errors": sum(int(m.get("item_errors", 0) or 0) for m in modules.values())}


def frames_seen(log_text: str) -> dict[str, int]:
    """Sum the per-window "new frame" counters printed by EVILEYE_PERF_DIAG."""
    totals = {"DetectorsIn": 0, "TrackersOut": 0}
    for stage, raw in PERF.findall(log_text):
        try:
            totals[stage] += sum(int(v) for v in eval(raw, {"__builtins__": {}}, {}).values())  # noqa: S307
        except Exception:
            continue
    return totals


def run_once(tree: Path, config: Path, timeout: float) -> dict:
    work = Path(tempfile.mkdtemp(prefix="rt_compare_"))
    runtime = work / "run"
    runtime.mkdir(mode=0o700)
    log_path = work / "run.log"
    env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), QT_QPA_PLATFORM="offscreen",
               PYTHONPATH=str(tree), EVILEYE_SITE_DIR=str(tree), EVILEYE_DATA_DIR=str(work / "data"),
               EVILEYE_PERF_DIAG="1", EVILEYE_PERF_DIAG_EVERY="1")
    begin = time.monotonic()
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "evileye.process", "--config", str(config), "--no-gui", "--autoclose"],
            cwd=str(tree), env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
        last_stats = None
        while proc.poll() is None and time.monotonic() - begin < timeout:
            stats = poll(runtime)
            if stats:
                last_stats = stats
            time.sleep(1.0)
        timed_out = proc.poll() is None
        if timed_out:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    ended = time.monotonic()
    started_at = None
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    seen = frames_seen(log_text)
    for line in log_text.splitlines():
        match = STARTED.match(line)
        if match:
            from datetime import datetime

            started_at = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S,%f")
            break
    total = ended - begin
    shutil.rmtree(work, ignore_errors=True) if not timed_out else None
    return {"total_sec": round(total, 1), "timed_out": timed_out, "exit": proc.returncode,
            "stats": last_stats, "detector_in": seen["DetectorsIn"], "tracker_out": seen["TrackersOut"],
            "started_wall": started_at.isoformat() if started_at else None,
            "log": str(log_path) if timed_out else None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--video", required=True)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--model", default="models/yolo11m.pt")
    parser.add_argument("--no-tracker", action="store_true")
    parser.add_argument("--execution-mode", choices=["thread", "process"], help="force detector/tracker mode (branch only)")
    parser.add_argument("--queue-size", type=int, help="queue_size for detectors and trackers (branch only)")
    parser.add_argument("--tree", action="append", required=True, help="label=path (repeatable)")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--report")
    args = parser.parse_args()

    work = Path(tempfile.mkdtemp(prefix="rt_clip_"))
    clip = make_clip(args.video, args.seconds, work)
    frames = frame_count(clip)
    results: dict[str, list[dict]] = {}
    for spec in args.tree:
        label, path = spec.split("=", 1)
        tree = Path(path).expanduser().resolve()
        config = tree / "configs" / CONFIG_NAME
        config.write_text(json.dumps(build_config(tree, clip, args.model, not args.no_tracker, args.queue_size, args.execution_mode), indent=2), encoding="utf-8")
        try:
            results[label] = []
            for index in range(args.runs):
                row = run_once(tree, config, args.timeout)
                row["frames"] = frames
                row["fps_total"] = round(frames / row["total_sec"], 2) if row["total_sec"] else None
                row["detector_in_pct"] = round(100.0 * row["detector_in"] / frames, 1)
                row["tracker_out_pct"] = round(100.0 * row["tracker_out"] / frames, 1)
                results[label].append(row)
                print(label, index + 1, json.dumps(row), flush=True)
        finally:
            config.unlink(missing_ok=True)
    print("\nlabel        runs  median_total_s  median_fps  exits")
    for label, rows in results.items():
        totals = [r["total_sec"] for r in rows if not r["timed_out"]]
        det = [r["detector_in_pct"] for r in rows if not r["timed_out"]]
        trk = [r["tracker_out_pct"] for r in rows if not r["timed_out"]]
        print(f"{label:<12} {len(rows):<5} {statistics.median(totals) if totals else 'n/a':<15} "
              f"{statistics.median(det) if det else 'n/a':<13} {statistics.median(trk) if trk else 'n/a':<13} "
              f"{[r['exit'] for r in rows]}")
    if args.report:
        Path(args.report).write_text(json.dumps({"frames": frames, "results": results}, indent=2), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
