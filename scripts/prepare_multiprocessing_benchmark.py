#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any
from datetime import datetime


DEFAULT_BASE_CONFIG = "configs/poly-videos-gst_gui_fixcheck_bench30.json"
DEFAULT_OUT_DIR = "reports/bench_multiprocessing/configs"
DEFAULT_MAX_CAMERAS = 4
PROCESSOR_SECTIONS = (
    "sources",
    "preprocessors",
    "detectors",
    "trackers",
    "mc_trackers",
    "attributes_roi",
    "attributes_classifier",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _source_ids(source: dict[str, Any]) -> list[int]:
    return [int(x) for x in source.get("source_ids", [])]


def _source_names(source: dict[str, Any]) -> list[str]:
    ids = _source_ids(source)
    names = source.get("source_names", ids)
    if not isinstance(names, list):
        names = [names]
    return [str(x) for x in names]


def _src_coords(source: dict[str, Any]) -> list[Any]:
    ids = _source_ids(source)
    coords = source.get("src_coords", [0])
    if not bool(source.get("split", False)):
        return [0 for _ in ids]
    if not isinstance(coords, list):
        return [coords for _ in ids]
    return coords


def _logical_cameras(config: dict[str, Any]) -> list[dict[str, Any]]:
    logical: list[dict[str, Any]] = []
    for source_index, source in enumerate(config.get("pipeline", {}).get("sources", []) or []):
        ids = _source_ids(source)
        names = _source_names(source)
        coords = _src_coords(source)
        for local_index, source_id in enumerate(ids):
            logical.append(
                {
                    "source_index": source_index,
                    "local_index": local_index,
                    "source_id": source_id,
                    "source_name": names[local_index] if local_index < len(names) else f"Cam{source_id}",
                    "src_coord": coords[local_index] if local_index < len(coords) else 0,
                    "camera": source.get("camera"),
                }
            )
    return logical


def _path_exists(camera: Any, config_dir: Path, repo_root: Path) -> bool:
    if not isinstance(camera, str) or not camera:
        return True
    if "://" in camera:
        return True
    path = Path(camera)
    if path.is_absolute():
        return path.exists()
    return (config_dir / path).exists() or (repo_root / path).exists()


def _validate_video_paths(config: dict[str, Any], config_path: Path, repo_root: Path) -> list[str]:
    missing: list[str] = []
    seen: set[str] = set()
    for source in config.get("pipeline", {}).get("sources", []) or []:
        camera = source.get("camera")
        if not isinstance(camera, str) or camera in seen:
            continue
        seen.add(camera)
        if not _path_exists(camera, config_path.parent, repo_root):
            missing.append(camera)
    return missing


def _selected_source_ids(selected: list[dict[str, Any]]) -> list[int]:
    return [int(item["source_id"]) for item in selected]


def _filter_source(source: dict[str, Any], selected_items: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    result = copy.deepcopy(source)
    result["execution_mode"] = mode
    result["source_ids"] = [int(item["source_id"]) for item in selected_items]
    result["source_names"] = [str(item["source_name"]) for item in selected_items]

    if bool(source.get("split", False)):
        result["split"] = True
        result["num_split"] = len(selected_items)
        result["src_coords"] = [item["src_coord"] for item in selected_items]
    else:
        result["split"] = False
        result["num_split"] = 0
        result["src_coords"] = [0]

    return result


def _filter_section_by_sources(items: list[Any], selected_ids: set[int], mode: str, *, section: str) -> list[Any]:
    filtered: list[Any] = []
    for item in items or []:
        if not isinstance(item, dict):
            filtered.append(copy.deepcopy(item))
            continue

        source_ids = item.get("source_ids")
        if isinstance(source_ids, list):
            keep_ids = [int(sid) for sid in source_ids if int(sid) in selected_ids]
            if not keep_ids:
                continue
            new_item = copy.deepcopy(item)
            new_item["source_ids"] = keep_ids
        else:
            new_item = copy.deepcopy(item)

        if section in PROCESSOR_SECTIONS:
            new_item["execution_mode"] = mode
        filtered.append(new_item)
    return filtered


def _filter_event_sources(value: Any, selected_ids: set[int]) -> Any:
    if not isinstance(value, dict):
        return value
    result = copy.deepcopy(value)
    sources = result.get("sources")
    if isinstance(sources, dict):
        result["sources"] = {
            str(source_id): source_value
            for source_id, source_value in sources.items()
            if int(source_id) in selected_ids
        }
    return result


def _normalize_runtime_flags(config: dict[str, Any], mode: str, selected_ids: list[int], *, enable_server: bool) -> None:
    pipeline = config.setdefault("pipeline", {})
    pipeline.setdefault("pipeline_class", "PipelineSurveillance")
    pipeline.setdefault("ipc_mode", "standard")

    visualizer = config.setdefault("visualizer", {})
    visualizer["source_ids"] = selected_ids
    visualizer["fps"] = [5 for _ in selected_ids]
    visualizer["num_width"] = max(1, math.ceil(math.sqrt(len(selected_ids))))
    visualizer["num_height"] = max(1, math.ceil(len(selected_ids) / visualizer["num_width"]))
    visualizer["gui_enabled"] = False
    visualizer["show_debug_info"] = True

    controller = config.setdefault("controller", {})
    controller["show_main_gui"] = False
    controller["gui_enabled"] = False
    controller["use_database"] = False
    controller["autoclose"] = True
    controller["perf_diag"] = True
    controller["perf_diag_every"] = 30
    controller["resource_stats_interval_sec"] = 5

    server = config.setdefault("server", {})
    server["enabled"] = bool(enable_server)
    server["execution_mode"] = mode

    record = config.setdefault("record", {})
    record["enabled"] = False
    record["continuous_recording_enabled"] = False
    record["event_recording_enabled"] = False

    storage_monitor = config.setdefault("storage_monitor", {})
    storage_monitor["enabled"] = False


def build_benchmark_config(
    base_config: dict[str, Any],
    selected: list[dict[str, Any]],
    mode: str,
    *,
    enable_server: bool,
) -> dict[str, Any]:
    config = copy.deepcopy(base_config)
    pipeline = config.setdefault("pipeline", {})
    selected_ids = _selected_source_ids(selected)
    selected_set = set(selected_ids)

    grouped_sources: dict[int, list[dict[str, Any]]] = {}
    for item in selected:
        grouped_sources.setdefault(int(item["source_index"]), []).append(item)

    base_sources = base_config.get("pipeline", {}).get("sources", []) or []
    pipeline["sources"] = [
        _filter_source(base_sources[source_index], grouped_sources[source_index], mode)
        for source_index in sorted(grouped_sources)
    ]

    for section in PROCESSOR_SECTIONS:
        if section == "sources":
            continue
        if section in pipeline:
            pipeline[section] = _filter_section_by_sources(
                pipeline.get(section, []) or [],
                selected_set,
                mode,
                section=section,
            )

    if "events_detectors" in config and isinstance(config["events_detectors"], dict):
        config["events_detectors"] = {
            name: _filter_event_sources(params, selected_set)
            for name, params in config["events_detectors"].items()
        }

    _normalize_runtime_flags(config, mode, selected_ids, enable_server=enable_server)
    return config


def prepare_configs(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = _repo_root()
    base_path = (repo_root / args.base_config).resolve()
    base_config = _load_json(base_path)
    logical = _logical_cameras(base_config)
    if not logical:
        raise SystemExit(f"В базовом конфиге не найдены источники: {base_path}")

    missing = _validate_video_paths(base_config, base_path, repo_root)
    if missing and not args.allow_missing:
        missing_list = "\n".join(f"  - {item}" for item in missing)
        raise SystemExit(
            "Не найдены видеофайлы из базового конфига. "
            "Укажите другой --base-config, исправьте пути или используйте --allow-missing "
            "для генерации шаблонов без проверки запуска:\n"
            f"{missing_list}"
        )

    max_cameras = min(args.max_cameras or DEFAULT_MAX_CAMERAS, len(logical))
    if max_cameras < 1:
        raise SystemExit("--max-cameras должен быть больше нуля")

    out_dir = (repo_root / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "base_config": str(base_path.relative_to(repo_root)),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "max_cameras": max_cameras,
        "modes": ["thread", "process"],
        "runs": [],
        "missing_video_paths": missing,
        "notes": [
            "Конфиги сгенерированы автоматически для A/B сравнения thread/process.",
            "Для честного сравнения не меняйте видео, модель и параметры FPS между режимами.",
        ],
    }

    for cameras in range(1, max_cameras + 1):
        selected = logical[:cameras]
        for mode in ("thread", "process"):
            generated = build_benchmark_config(
                base_config,
                selected,
                mode,
                enable_server=args.enable_server,
            )
            filename = f"bench_{cameras:02d}cam_{mode}.json"
            config_path = out_dir / filename
            _write_json(config_path, generated)
            manifest["runs"].append(
                {
                    "camera_count": cameras,
                    "mode": mode,
                    "config": str(config_path.relative_to(repo_root)),
                    "source_ids": _selected_source_ids(selected),
                    "source_names": [item["source_name"] for item in selected],
                }
            )

    manifest_path = out_dir / "manifest.json"
    _write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Подготовить конфиги для сравнения thread/process на разном числе камер."
    )
    parser.add_argument("--base-config", default=DEFAULT_BASE_CONFIG)
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-cameras", type=int, default=None)
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Сгенерировать конфиги даже если видеофайлы из base-config не найдены.",
    )
    parser.add_argument(
        "--enable-server",
        action="store_true",
        help="Оставить web server включенным и переключать его execution_mode вместе с пайплайном.",
    )
    args = parser.parse_args()

    manifest = prepare_configs(args)
    print("Конфиги benchmark подготовлены.")
    print(f"Базовый конфиг: {manifest['base_config']}")
    print(f"Максимум камер: {manifest['max_cameras']}")
    print(f"Количество запусков: {len(manifest['runs'])}")
    if manifest["missing_video_paths"]:
        print("Внимание: часть видеофайлов отсутствует, конфиги требуют проверки путей.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
