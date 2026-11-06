#!/usr/bin/env python3
"""Cut and restore an RTSP stream under a running EvilEye and check how it recovers.

A looped video is published with ``cvlc`` (VLC RTSP server). EvilEye runs headless against it
in an isolated runtime directory, and its runtime telemetry is polled through the control
socket. The stream is stopped for ``--offline-sec`` seconds and restarted; the check passes
when the source reports the disconnect, reconnects without help, and stops being degraded
once ``EVILEYE_DEGRADED_WINDOW_SEC`` has passed.

    python scripts/rtsp_disconnect_check.py --video ~/EvilEye/videos/x.mp4 --backend gst

Linux only (uses ``cvlc``, process groups and the control Unix socket). Exit code 0 on pass.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_CONFIG = ROOT / "configs" / "poly-cameras-gst-capture-only.json"


def build_config(backend: str, url: str, with_detector: bool) -> dict:
    base = json.loads(BASE_CONFIG.read_text(encoding="utf-8"))
    cfg = copy.deepcopy(base)
    source = copy.deepcopy(base["pipeline"]["sources"][0])
    source.update({"camera": url, "source_names": ["RtspCheck"], "source_ids": [0], "split": False, "num_split": 0})
    source.pop("src_coords", None)
    if backend == "opencv":
        source["type"] = "VideoCaptureOpencv"
        source["apiPreference"] = "CAP_FFMPEG"
    cfg["pipeline"]["sources"] = [source]
    cfg["pipeline"]["detectors"] = base["pipeline"].get("detectors", []) if with_detector else []
    cfg["pipeline"]["trackers"] = base["pipeline"].get("trackers", []) if with_detector else []
    cfg["pipeline"]["mc_trackers"] = []
    cfg["controller"].update({"gui_enabled": False, "show_main_gui": False, "autoclose": False, "auto_restart": False})
    cfg["record"].update({"enabled": False, "continuous_recording_enabled": False})
    cfg["storage_monitor"]["enabled"] = False
    cfg["server"]["enabled"] = False
    cfg["visualizer"].update({"source_ids": [0], "fps": [30]})
    return cfg


def port_open(port: int) -> bool:
    """Whether something listens on ``port``, without connecting to it.

    A bare connect/close makes the VLC RTSP server answer 500 to every later client.
    """
    result = subprocess.run(["ss", "-ltnH", f"sport = :{port}"], capture_output=True, text=True)
    return bool(result.stdout.strip())


class Stream:
    """The cvlc publisher; ``stop`` simulates a camera that goes away."""

    def __init__(self, video: str, port: int, warmup_sec: float = 7.0, log_path: Path | None = None):
        self.video, self.port, self.proc = video, port, None
        self.warmup_sec = warmup_sec
        self.log_path = log_path

    def start(self) -> None:
        sout = f"#rtp{{sdp=rtsp://:{self.port}/test}}"
        sink = open(self.log_path, "a", encoding="utf-8") if self.log_path else subprocess.DEVNULL
        self.proc = subprocess.Popen(
            ["cvlc", self.video, "--loop", "--no-audio", "-vv", "--sout", sout, "--sout-keep"],
            stdout=sink, stderr=subprocess.STDOUT, start_new_session=True,
        )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not port_open(self.port):
            time.sleep(0.2)
        if not port_open(self.port):
            raise RuntimeError("cvlc did not open the RTSP port")
        # VLC answers 500 to DESCRIBE until it has analysed the file (about 5 s for a 2.7K
        # stream) and stays unhappy after an early request, so do not let clients in before.
        time.sleep(self.warmup_sec)

    def stop(self) -> None:
        if self.proc is not None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
                self.proc.wait(timeout=10)
            except Exception:
                os.killpg(self.proc.pid, signal.SIGKILL)
            self.proc = None
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and port_open(self.port):
            time.sleep(0.2)


def snapshot(runtime_dir: Path) -> dict | None:
    os.environ["XDG_RUNTIME_DIR"] = str(runtime_dir)
    sys.path.insert(0, str(ROOT))
    from evileye.api.core.control_ipc import send_control_command

    reply = send_control_command({"cmd": "get_runtime_stats"}, timeout=3.0)
    if not isinstance(reply, dict) or not reply.get("ok"):
        return None
    pipeline = (reply.get("stats") or {}).get("components", {}).get("pipeline", {})
    sources = pipeline.get("module_instances") or {}
    source = next((v for k, v in sources.items() if k.startswith("sources:")), None)
    if source is None:
        return None
    health = source.get("capture_health") or {}
    return {
        "working": bool(health.get("working")),
        "disconnects": int(health.get("disconnect_count") or 0),
        "reconnects": int(health.get("reconnect_count") or 0),
        "degraded": bool(source.get("degraded")),
        "failed": bool(source.get("failed")),
        "worker_running": bool(source.get("worker_running")),
        "pipeline_degraded": bool(pipeline.get("degraded")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--video", required=True)
    parser.add_argument("--backend", choices=["gst", "opencv"], default="gst")
    parser.add_argument("--port", type=int, default=8554)
    parser.add_argument("--detector", action="store_true", help="keep detectors/trackers from the base config")
    parser.add_argument("--steady-sec", type=float, default=20)
    parser.add_argument("--offline-sec", type=float, default=25)
    parser.add_argument("--degraded-window-sec", type=float, default=15)
    parser.add_argument("--recover-timeout-sec", type=float, default=120)
    parser.add_argument("--report", help="write the timeline and verdict as JSON")
    args = parser.parse_args()

    work = Path(tempfile.mkdtemp(prefix="rtsp_check_"))
    runtime_dir = work / "run"
    runtime_dir.mkdir(mode=0o700)
    (runtime_dir / "evileye").mkdir(exist_ok=True)
    config_path = ROOT / "configs" / f"_rtsp_check_{args.backend}.json"
    url = f"rtsp://127.0.0.1:{args.port}/test"
    config_path.write_text(json.dumps(build_config(args.backend, url, args.detector), indent=2), encoding="utf-8")

    env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime_dir), QT_QPA_PLATFORM="offscreen",
               EVILEYE_DEGRADED_WINDOW_SEC=str(args.degraded_window_sec))
    log = open(work / "evileye.log", "w", encoding="utf-8")
    stream = Stream(args.video, args.port, log_path=work / "vlc.log")
    app = None
    timeline: list[dict] = []
    started = time.monotonic()

    def sample(phase: str) -> dict | None:
        row = snapshot(runtime_dir)
        if row is not None:
            row = dict(row, t=round(time.monotonic() - started, 1), phase=phase)
            timeline.append(row)
        return row

    def wait_for(phase: str, predicate, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            row = sample(phase)
            if row is not None and predicate(row):
                return True
            time.sleep(1.0)
        return False

    checks: dict[str, bool] = {}
    try:
        stream.start()
        app = subprocess.Popen(
            [sys.executable, "-m", "evileye.process", "--config", str(config_path), "--no-gui", "--log-level", "INFO"],
            cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
        checks["connected"] = wait_for("warmup", lambda r: r["working"], 90)
        if checks["connected"]:
            end = time.monotonic() + args.steady_sec
            while time.monotonic() < end:
                sample("steady")
                time.sleep(1.0)
        before = timeline[-1] if timeline else {"disconnects": 0, "reconnects": 0}
        stream.stop()
        checks["disconnect_reported"] = wait_for(
            "offline", lambda r: (not r["working"]) or r["disconnects"] > before["disconnects"], args.offline_sec
        )
        remaining = args.offline_sec
        end = time.monotonic() + remaining
        while time.monotonic() < end:
            sample("offline")
            time.sleep(1.0)
        checks["no_crash_while_offline"] = app.poll() is None
        stream.start()
        checks["reconnected"] = wait_for(
            "recovery", lambda r: r["working"] and r["reconnects"] > before["reconnects"], args.recover_timeout_sec
        )
        checks["not_failed"] = bool(timeline) and not any(r["failed"] for r in timeline)
        checks["degraded_clears"] = wait_for(
            "settle", lambda r: not r["degraded"] and r["working"], args.degraded_window_sec + 45
        )
    finally:
        stream.stop()
        if app is not None and app.poll() is None:
            os.killpg(app.pid, signal.SIGTERM)
            try:
                app.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(app.pid, signal.SIGKILL)
        log.close()
        config_path.unlink(missing_ok=True)

    leftovers = subprocess.run(["pgrep", "-f", str(config_path)], capture_output=True, text=True).stdout.split()
    checks["clean_shutdown"] = not leftovers
    passed = all(checks.values())
    last = timeline[-1] if timeline else {}
    print(json.dumps({"backend": args.backend, "checks": checks, "last": last, "log": str(work / "evileye.log")}, indent=2))
    if args.report:
        Path(args.report).write_text(
            json.dumps({"checks": checks, "timeline": timeline, "passed": passed}, indent=2), encoding="utf-8"
        )
    if passed:
        shutil.rmtree(work, ignore_errors=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
