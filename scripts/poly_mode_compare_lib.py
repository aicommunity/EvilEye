"""Shared helpers for poly-videos process vs thread benchmark."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = REPO_ROOT / "reports" / "poly_videos_mode_compare"

COMPARE_CONFIGS: list[dict[str, str]] = [
    {
        "config": "configs/poly-videos.json",
        "capture": "opencv",
        "mode": "process",
        "slug": "poly-videos_opencv_process",
    },
    {
        "config": "configs/poly-videos-thread.json",
        "capture": "opencv",
        "mode": "thread",
        "slug": "poly-videos_opencv_thread",
    },
    {
        "config": "configs/poly-videos-gst.json",
        "capture": "gst",
        "mode": "process",
        "slug": "poly-videos_gst_process",
    },
    {
        "config": "configs/poly-videos-gst-thread.json",
        "capture": "gst",
        "mode": "thread",
        "slug": "poly-videos_gst_thread",
    },
]

EXPECTED_DIFF_KEYS = re.compile(
    r"(^|\.)execution_mode$|\.type$|\.apiPreference$|gstreamer",
    re.IGNORECASE,
)


def flatten_dict(data: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            out.update(flatten_dict(value, path))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            out.update(flatten_dict(value, f"{prefix}[{index}]"))
    else:
        out[prefix] = data
    return out


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def config_video_paths(cfg: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for source in (cfg.get("pipeline", {}) or {}).get("sources", []) or []:
        if isinstance(source, dict):
            camera = source.get("camera")
            if camera:
                paths.append(str(camera))
    return paths


def _absolutize_model_paths(cfg: dict[str, Any], repo_root: Path = REPO_ROOT) -> None:
    """Avoid concurrent YOLO downloads from MP workers (race on /tmp/models)."""
    pipeline = cfg.get("pipeline")
    if not isinstance(pipeline, dict):
        return
    for section in ("detectors", "attributes_detectors"):
        for item in pipeline.get(section) or []:
            if not isinstance(item, dict):
                continue
            model = item.get("model")
            if not model or Path(str(model)).is_absolute():
                continue
            candidate = (repo_root / str(model)).resolve()
            if candidate.is_file():
                item["model"] = str(candidate)


def _filter_pipeline_section(
    items: list[Any] | None,
    allowed_source_ids: set[int],
) -> list[Any]:
    if not items or not allowed_source_ids:
        return list(items or [])
    out: list[Any] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sids = item.get("source_ids") or []
        if any(int(s) in allowed_source_ids for s in sids):
            out.append(item)
    return out


def build_bench_overlay_slice(
    base_path: Path,
    *,
    source_ids: list[int] | None = None,
    num_detection_threads: int | None = None,
    perf_diag: bool = True,
    perf_diag_every: int = 30,
) -> Path:
    """Bench overlay: subset of sources/detectors/trackers or thread count tweak."""
    cfg = load_config(base_path)
    _absolutize_model_paths(cfg)
    pipeline = cfg.get("pipeline")
    if source_ids is not None and isinstance(pipeline, dict):
        allowed = set(int(s) for s in source_ids)
        pipeline["sources"] = _filter_pipeline_section(pipeline.get("sources"), allowed)
        for key in ("detectors", "trackers", "mc_trackers", "attributes_detectors"):
            if key in pipeline:
                pipeline[key] = _filter_pipeline_section(pipeline.get(key), allowed)
    if num_detection_threads is not None and isinstance(pipeline, dict):
        for det in pipeline.get("detectors") or []:
            if isinstance(det, dict):
                det["num_detection_threads"] = int(num_detection_threads)
    controller = cfg.setdefault("controller", {})
    if isinstance(controller, dict):
        controller["perf_diag"] = perf_diag
        controller["perf_diag_every"] = perf_diag_every
    fd, tmp_name = tempfile.mkstemp(suffix=".json", prefix="evileye_bench_")
    import os

    os.close(fd)
    tmp_path = Path(tmp_name)
    tmp_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    return tmp_path


def apply_env_overrides(env: dict[str, str] | None = None) -> dict[str, str]:
    """Copy env and apply standard MP bench overrides from os.environ."""
    import os

    out = dict(env or os.environ)
    for key in (
        "EVILEYE_MP_QUEUE_SCALE",
        "EVILEYE_MP_DRAIN_POLL_SEC",
        "EVILEYE_PIPELINE_SYNC_MP",
        "EVILEYE_PIPELINE_SYNC_MP_MS",
        "EVILEYE_CONTROLLER_BACKPRESSURE",
        "EVILEYE_PERF_DIAG",
        "EVILEYE_PERF_DIAG_EVERY",
        "EVILEYE_PIPELINE_TIMELINE",
    ):
        val = os.environ.get(key)
        if val is not None:
            out[key] = val
    return out


def write_bench_config(
    base_path: Path,
    *,
    perf_diag: bool = True,
    perf_diag_every: int = 30,
) -> Path:
    """Runtime overlay: controller perf_diag without editing repo configs."""
    import os

    source_ids = None
    raw_sids = os.environ.get("EVILEYE_BENCH_OVERLAY_SOURCE_IDS", "").strip()
    if raw_sids:
        source_ids = [int(x.strip()) for x in raw_sids.split(",") if x.strip()]
    num_threads = None
    raw_nt = os.environ.get("EVILEYE_BENCH_OVERLAY_NUM_THREADS", "").strip()
    if raw_nt:
        num_threads = int(raw_nt)
    return build_bench_overlay_slice(
        base_path,
        source_ids=source_ids,
        num_detection_threads=num_threads,
        perf_diag=perf_diag,
        perf_diag_every=perf_diag_every,
    )


def build_manifest(*, runs_per_config: int = 5) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    for spec in COMPARE_CONFIGS:
        for run_index in range(1, runs_per_config + 1):
            runs.append(
                {
                    "config": spec["config"],
                    "capture": spec["capture"],
                    "mode": spec["mode"],
                    "slug": spec["slug"],
                    "run_index": run_index,
                    "log": f"logs/{spec['slug']}_run{run_index:02d}.log",
                    "samples": f"samples/{spec['slug']}_run{run_index:02d}.csv",
                }
            )
    return {
        "description": "poly-videos opencv/gst x process/thread",
        "runs_per_config": runs_per_config,
        "configs": COMPARE_CONFIGS,
        "runs": runs,
    }


def compare_config_pair(path_a: Path, path_b: Path) -> list[dict[str, Any]]:
    flat_a = flatten_dict(load_config(path_a))
    flat_b = flatten_dict(load_config(path_b))
    diffs: list[dict[str, Any]] = []
    for key in sorted(set(flat_a) | set(flat_b)):
        va, vb = flat_a.get(key), flat_b.get(key)
        if va != vb:
            diffs.append(
                {
                    "key": key,
                    "a": va,
                    "b": vb,
                    "expected": bool(EXPECTED_DIFF_KEYS.search(key)),
                }
            )
    return diffs
