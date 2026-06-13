#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import prepare_multiprocessing_benchmark as mp_bench

# This orchestration script intentionally reuses helper functions from the
# existing benchmark generator to keep config slicing identical.
# pylint: disable=protected-access


DEFAULT_OUT_DIR = "reports/linux_perf_matrix/configs"
DEFAULT_SCENARIOS = ("capture", "detection", "tracking", "visualization", "full")
DEFAULT_LAYOUTS = ("process_detector", "process_capture_detector", "process_full")
DEFAULT_DEVICES = ("cpu", "cuda:0")

SCENARIO_LABELS = {
    "capture": "только захват",
    "detection": "захват + обнаружение",
    "tracking": "захват + обнаружение + отслеживание",
    "visualization": "захват + визуализация",
    "full": "полный пайплайн",
}

LAYOUT_LABELS = {
    "process_detector": "в отдельном процессе только обнаружение",
    "process_capture_detector": "в отдельных процессах захват и обнаружение",
    "process_full": "захват, обнаружение и отслеживание в отдельных процессах (по одному процессу на камеру)",
}

DEVICE_LABELS = {
    "cpu": "CPU",
    "cuda:0": "GPU",
}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe_name(value: str) -> str:
    return (
        value.lower()
        .replace(":", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
    )


def _set_detector_device(config: dict[str, Any], device: str) -> None:
    for detector in config.get("pipeline", {}).get("detectors", []) or []:
        if isinstance(detector, dict):
            detector["device"] = device


def _drop_pipeline_sections(config: dict[str, Any], sections: set[str]) -> None:
    pipeline = config.setdefault("pipeline", {})
    for section in sections:
        if section in pipeline:
            pipeline[section] = []


def _disable_event_work(config: dict[str, Any]) -> None:
    config["events_detectors"] = {}
    config["events_processor"] = {}


def _apply_scenario(config: dict[str, Any], scenario: str) -> None:
    if scenario in {"capture", "visualization"}:
        _drop_pipeline_sections(
            config,
            {
                "preprocessors",
                "detectors",
                "trackers",
                "mc_trackers",
                "attributes_roi",
                "attributes_classifier",
            },
        )
        _disable_event_work(config)
        return

    if scenario == "detection":
        _drop_pipeline_sections(
            config,
            {
                "trackers",
                "mc_trackers",
                "attributes_roi",
                "attributes_classifier",
            },
        )
        _disable_event_work(config)
        return

    if scenario == "tracking":
        _drop_pipeline_sections(
            config,
            {
                "mc_trackers",
                "attributes_roi",
                "attributes_classifier",
            },
        )
        _disable_event_work(config)
        return

    if scenario == "full":
        return

    raise SystemExit(f"Неизвестный сценарий пайплайна: {scenario}")


def _layout_flags(layout: str) -> tuple[bool, bool]:
    if layout == "process_detector":
        return True, False
    if layout == "process_capture_detector":
        return True, True
    if layout == "process_full":
        return False, False
    raise SystemExit(f"Неизвестная схема multiprocessing: {layout}")


def _config_for_run(
    base_config: dict[str, Any],
    selected: list[dict[str, Any]],
    *,
    mode: str,
    layout: str,
    scenario: str,
    device: str,
    shared_detector_pool: bool,
    target_fps: float | None,
    num_detection_threads: int | None,
) -> dict[str, Any]:
    detector_process_only, capture_process_also = _layout_flags(layout)
    if mode == "thread":
        detector_process_only = False
        capture_process_also = False

    config = mp_bench.build_benchmark_config(
        base_config,
        selected,
        mode,
        enable_server=False,
        shared_detector_pool=shared_detector_pool,
        detector_process_only=detector_process_only,
        capture_process_also=capture_process_also,
    )
    _apply_scenario(config, scenario)
    _set_detector_device(config, device)
    mp_bench._normalize_detection_threads(config, num_detection_threads)
    mp_bench._normalize_target_fps(config, target_fps)
    return config


def _result_dir_for_run(
    results_root: str,
    device_key: str,
    scenario: str,
    layout: str,
) -> str:
    root = results_root.rstrip("/")
    return f"{root}/{device_key}/{scenario}/{layout}"


def prepare_matrix(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = mp_bench._repo_root()
    results_root = str(args.results_root).rstrip("/")
    base_path = (repo_root / args.base_config).resolve()
    base_config = mp_bench._load_json(base_path)
    requested_max_cameras = args.max_cameras or mp_bench.DEFAULT_MAX_CAMERAS
    if args.repeat_cameras:
        base_config = mp_bench._expand_config_repeating_cameras(base_config, requested_max_cameras)

    logical = mp_bench._logical_cameras(base_config)
    if not logical:
        raise SystemExit(f"В базовом конфиге не найдены источники: {base_path}")

    missing = mp_bench._validate_video_paths(base_config, base_path, repo_root)
    if missing and not args.allow_missing:
        missing_list = "\n".join(f"  - {item}" for item in missing)
        raise SystemExit(
            "Не найдены видеофайлы из базового конфига. Исправьте пути, "
            "укажите другой --base-config или используйте --allow-missing:\n"
            f"{missing_list}"
        )

    max_cameras = min(requested_max_cameras, len(logical))
    out_dir = (repo_root / args.out_dir).resolve()
    matrix: dict[str, Any] = {
        "base_config": str(base_path.relative_to(repo_root)),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "results_root": results_root,
        "shared_detector_pool": bool(args.shared_detector_pool),
        "max_cameras": max_cameras,
        "devices": list(args.devices),
        "scenarios": list(args.scenarios),
        "layouts": list(args.layouts),
        "runs": [],
        "missing_video_paths": missing,
        "notes": [
            "Каждый manifest содержит парное сравнение thread/process для одной схемы multiprocessing.",
            "Запись видео, база данных, storage monitor и GUI отключаются в сгенерированных runtime-конфигах.",
            "Сценарий visualization оставляет только захват и headless-визуализацию; FPS визуализации также измеряется в остальных сценариях.",
            "Для process_full при --no-shared-detector-pool на каждую камеру создаются отдельные entries sources/detectors/trackers.",
        ],
    }

    for device in args.devices:
        device_key = _safe_name(device)
        for scenario in args.scenarios:
            for layout in args.layouts:
                manifest_dir = out_dir / device_key / scenario / layout
                manifest: dict[str, Any] = {
                    "base_config": str(base_path.relative_to(repo_root)),
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "max_cameras": max_cameras,
                    "modes": ["thread", "process"],
                    "repeat_cameras": bool(args.repeat_cameras),
                    "shared_detector_pool": bool(args.shared_detector_pool),
                    "per_camera_components": not bool(args.shared_detector_pool),
                    "detector_process_only": layout in {"process_detector", "process_capture_detector"},
                    "capture_process_also": layout == "process_capture_detector",
                    "process_all_stages": layout == "process_full",
                    "device": device,
                    "device_label": DEVICE_LABELS.get(device, device),
                    "scenario": scenario,
                    "scenario_label": SCENARIO_LABELS[scenario],
                    "layout": layout,
                    "layout_label": LAYOUT_LABELS[layout],
                    "runs": [],
                    "missing_video_paths": missing,
                }
                for cameras in range(1, max_cameras + 1):
                    selected = logical[:cameras]
                    for mode in ("thread", "process"):
                        generated = _config_for_run(
                            copy.deepcopy(base_config),
                            selected,
                            mode=mode,
                            layout=layout,
                            scenario=scenario,
                            device=device,
                            shared_detector_pool=bool(args.shared_detector_pool),
                            target_fps=args.target_fps,
                            num_detection_threads=args.num_detection_threads,
                        )
                        mp_bench._normalize_local_file_references(generated, base_path.parent, repo_root)
                        filename = f"bench_{cameras:02d}cam_{mode}.json"
                        config_path = manifest_dir / filename
                        _write_json(config_path, generated)
                        manifest["runs"].append(
                            {
                                "camera_count": cameras,
                                "mode": mode,
                                "config": mp_bench._path_for_manifest(config_path, repo_root),
                                "source_ids": mp_bench._selected_source_ids(selected),
                                "source_names": [item["source_name"] for item in selected],
                            }
                        )

                manifest_path = manifest_dir / "manifest.json"
                _write_json(manifest_path, manifest)
                matrix["runs"].append(
                    {
                        "device": device,
                        "device_label": DEVICE_LABELS.get(device, device),
                        "scenario": scenario,
                        "scenario_label": SCENARIO_LABELS[scenario],
                        "layout": layout,
                        "layout_label": LAYOUT_LABELS[layout],
                        "manifest": mp_bench._path_for_manifest(manifest_path, repo_root),
                        "result_dir": _result_dir_for_run(
                            results_root, device_key, scenario, layout
                        ),
                    }
                )

    matrix_path = out_dir / "matrix_manifest.json"
    _write_json(matrix_path, matrix)
    return matrix


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Подготовить Linux-матрицу benchmark: CPU/GPU, сценарии пайплайна и схемы multiprocessing."
    )
    parser.add_argument("--base-config", default="configs/multi_videos.json")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--results-root",
        default="reports/linux_perf_matrix/results",
        help="Корень каталогов результатов (пути в matrix_manifest.json).",
    )
    parser.add_argument("--max-cameras", type=int, default=4)
    parser.add_argument("--repeat-cameras", action="store_true")
    parser.add_argument("--allow-missing", action="store_true")
    parser.add_argument("--target-fps", type=float, default=30.0)
    parser.add_argument("--num-detection-threads", type=int, default=1)
    parser.add_argument(
        "--shared-detector-pool",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Объединять совместимые детекторы в один пул (для per-camera MP используйте --no-shared-detector-pool).",
    )
    parser.add_argument("--devices", nargs="+", default=list(DEFAULT_DEVICES))
    parser.add_argument("--scenarios", nargs="+", choices=DEFAULT_SCENARIOS, default=list(DEFAULT_SCENARIOS))
    parser.add_argument("--layouts", nargs="+", choices=DEFAULT_LAYOUTS, default=list(DEFAULT_LAYOUTS))
    args = parser.parse_args()

    matrix = prepare_matrix(args)
    print("Матрица benchmark подготовлена.")
    print(f"Базовый конфиг: {matrix['base_config']}")
    print(f"Максимум камер: {matrix['max_cameras']}")
    print(f"Количество manifest: {len(matrix['runs'])}")
    print(f"Matrix manifest: {args.out_dir}/matrix_manifest.json")
    if matrix["missing_video_paths"]:
        print("Внимание: часть видеофайлов отсутствует, конфиги требуют проверки путей.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
