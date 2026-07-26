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


def _path_for_manifest(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


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


def _processor_for_source(items: list[Any], source_id: int) -> dict[str, Any] | None:
    for item in items or []:
        if not isinstance(item, dict):
            continue
        source_ids = item.get("source_ids")
        if isinstance(source_ids, list) and source_id in {int(sid) for sid in source_ids}:
            return item
    return None


def _single_camera_source(source: dict[str, Any], logical_camera: dict[str, Any], new_id: int) -> dict[str, Any]:
    result = copy.deepcopy(source)
    result["source_ids"] = [new_id]
    result["source_names"] = [f"Cam{new_id + 1}"]
    if bool(source.get("split", False)):
        result["split"] = True
        result["num_split"] = 1
        result["src_coords"] = [copy.deepcopy(logical_camera.get("src_coord", 0))]
    else:
        result["split"] = False
        result["num_split"] = 0
        result["src_coords"] = [0]
    return result


def _expand_config_repeating_cameras(config: dict[str, Any], target_count: int) -> dict[str, Any]:
    """Repeat available video definitions to build a larger logical camera set."""
    logical = _logical_cameras(config)
    if target_count <= len(logical):
        return config
    if not logical:
        raise SystemExit("Нельзя повторить источники: в базовом конфиге нет логических камер.")

    expanded = copy.deepcopy(config)
    pipeline = expanded.setdefault("pipeline", {})
    base_pipeline = config.get("pipeline", {})
    base_sources = base_pipeline.get("sources", []) or []

    pipeline["sources"] = []
    duplicated_sections: dict[str, list[Any]] = {
        section: [] for section in PROCESSOR_SECTIONS if section not in {"sources", "mc_trackers"}
    }

    for new_id in range(target_count):
        template = logical[new_id % len(logical)]
        old_source_id = int(template["source_id"])
        source_template = base_sources[int(template["source_index"])]
        pipeline["sources"].append(_single_camera_source(source_template, template, new_id))

        for section, duplicated in duplicated_sections.items():
            items = base_pipeline.get(section, []) or []
            processor = _processor_for_source(items, old_source_id)
            if processor is None:
                continue
            new_processor = copy.deepcopy(processor)
            new_processor["source_ids"] = [new_id]
            duplicated.append(new_processor)

    for section, duplicated in duplicated_sections.items():
        if section in pipeline or duplicated:
            pipeline[section] = duplicated

    mc_trackers = base_pipeline.get("mc_trackers", []) or []
    if mc_trackers:
        new_mc = copy.deepcopy(mc_trackers[0])
        if isinstance(new_mc, dict):
            new_mc["source_ids"] = list(range(target_count))
            pipeline["mc_trackers"] = [new_mc]

    return expanded


def _path_exists(camera: Any, config_dir: Path, repo_root: Path) -> bool:
    if not isinstance(camera, str) or not camera:
        return True
    if camera.isdigit():
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


def _resolve_local_path(value: str, config_dir: Path, repo_root: Path) -> str:
    if not value or value.isdigit() or "://" in value:
        return value
    path = Path(value)
    if path.is_absolute():
        return value
    config_relative = config_dir / path
    if config_relative.exists():
        return str(config_relative.resolve())
    repo_relative = repo_root / path
    if repo_relative.exists():
        return str(repo_relative.resolve())
    return value


def _normalize_local_file_references(config: dict[str, Any], config_dir: Path, repo_root: Path) -> None:
    for source in config.get("pipeline", {}).get("sources", []) or []:
        if isinstance(source, dict) and isinstance(source.get("camera"), str):
            source["camera"] = _resolve_local_path(source["camera"], config_dir, repo_root)

    for section in PROCESSOR_SECTIONS:
        if section == "sources":
            continue
        for item in config.get("pipeline", {}).get(section, []) or []:
            if isinstance(item, dict) and isinstance(item.get("model"), str):
                item["model"] = _resolve_local_path(item["model"], config_dir, repo_root)


def _normalize_detection_threads(config: dict[str, Any], num_threads: int | None) -> None:
    if num_threads is None:
        return
    for detector in config.get("pipeline", {}).get("detectors", []) or []:
        if isinstance(detector, dict):
            detector["num_detection_threads"] = max(1, int(num_threads))


def _detector_pool_key(detector: dict[str, Any]) -> str:
    ignored = {"source_ids", "roi", "num_detection_threads", "execution_mode"}
    comparable = {
        key: value
        for key, value in detector.items()
        if key not in ignored
    }
    return json.dumps(comparable, ensure_ascii=False, sort_keys=True, default=str)


def _roi_for_source(detector: dict[str, Any], source_id: int) -> Any:
    source_ids = [int(item) for item in detector.get("source_ids", []) or []]
    roi = detector.get("roi", [])
    if not isinstance(roi, list):
        return []
    if source_id in source_ids:
        index = source_ids.index(source_id)
        if index < len(roi):
            return copy.deepcopy(roi[index])
    if len(roi) == 1:
        return copy.deepcopy(roi[0])
    return []


def _merge_shared_detector_pool(config: dict[str, Any], enabled: bool) -> None:
    """Объединить совместимые detector entries в один multi-source detector.

    Для честного A/B включается для thread и process: сравнивается одна общая модель
    во всех камерах, а не N отдельных инстансов против одного пула.
    """
    if not enabled:
        return
    pipeline = config.get("pipeline", {})
    detectors = pipeline.get("detectors", [])
    if not isinstance(detectors, list) or len(detectors) < 2:
        return

    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    passthrough: list[Any] = []
    for detector in detectors:
        if not isinstance(detector, dict):
            passthrough.append(copy.deepcopy(detector))
            continue
        source_ids = detector.get("source_ids")
        if not isinstance(source_ids, list) or not source_ids:
            passthrough.append(copy.deepcopy(detector))
            continue

        key = _detector_pool_key(detector)
        if key not in groups:
            pooled = copy.deepcopy(detector)
            pooled["source_ids"] = []
            pooled["roi"] = []
            pooled["num_detection_threads"] = max(1, int(detector.get("num_detection_threads", 1) or 1))
            groups[key] = pooled
            order.append(key)

        pooled = groups[key]
        for source_id in [int(item) for item in source_ids]:
            if source_id in pooled["source_ids"]:
                continue
            pooled["source_ids"].append(source_id)
            pooled["roi"].append(_roi_for_source(detector, source_id))

    pipeline["detectors"] = [groups[key] for key in order] + passthrough


def _normalize_target_fps(config: dict[str, Any], target_fps: float | None) -> None:
    if target_fps is None:
        return
    fps = max(1.0, float(target_fps))
    pipeline = config.get("pipeline", {})
    for source in pipeline.get("sources", []) or []:
        if isinstance(source, dict):
            source["desired_fps"] = fps
    visualizer = config.setdefault("visualizer", {})
    source_ids = visualizer.get("source_ids") or []
    visualizer["fps"] = [fps for _ in source_ids]
    controller = config.setdefault("controller", {})
    controller["fps"] = fps


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


def _section_execution_mode(
    mode: str,
    section: str,
    *,
    detector_process_only: bool,
    capture_process_also: bool,
) -> str:
    if not (detector_process_only and mode == "process"):
        return mode
    if section == "detectors":
        return "process"
    if capture_process_also and section == "sources":
        return "process"
    return "thread"


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
    shared_detector_pool: bool,
    detector_process_only: bool,
    capture_process_also: bool,
) -> dict[str, Any]:
    config = copy.deepcopy(base_config)
    pipeline = config.setdefault("pipeline", {})
    selected_ids = _selected_source_ids(selected)
    selected_set = set(selected_ids)

    grouped_sources: dict[int, list[dict[str, Any]]] = {}
    for item in selected:
        grouped_sources.setdefault(int(item["source_index"]), []).append(item)

    base_sources = base_config.get("pipeline", {}).get("sources", []) or []
    source_mode = _section_execution_mode(
        mode,
        "sources",
        detector_process_only=detector_process_only,
        capture_process_also=capture_process_also,
    )
    pipeline["sources"] = [
        _filter_source(base_sources[source_index], grouped_sources[source_index], source_mode)
        for source_index in sorted(grouped_sources)
    ]

    for section in PROCESSOR_SECTIONS:
        if section == "sources":
            continue
        if section in pipeline:
            section_mode = _section_execution_mode(
                mode,
                section,
                detector_process_only=detector_process_only,
                capture_process_also=capture_process_also,
            )
            pipeline[section] = _filter_section_by_sources(
                pipeline.get(section, []) or [],
                selected_set,
                section_mode,
                section=section,
            )

    if "events_detectors" in config and isinstance(config["events_detectors"], dict):
        config["events_detectors"] = {
            name: _filter_event_sources(params, selected_set)
            for name, params in config["events_detectors"].items()
        }

    runtime_mode = "thread" if detector_process_only and mode == "process" else mode
    _normalize_runtime_flags(config, runtime_mode, selected_ids, enable_server=enable_server)
    _merge_shared_detector_pool(config, enabled=shared_detector_pool)
    return config


def prepare_configs(args: argparse.Namespace) -> dict[str, Any]:
    capture_process_also = bool(getattr(args, "capture_process_also", False))
    if capture_process_also and not bool(getattr(args, "detector_process_only", False)):
        raise SystemExit("--capture-process-also имеет смысл только вместе с --detector-process-only.")

    repo_root = _repo_root()
    base_path = (repo_root / args.base_config).resolve()
    base_config = _load_json(base_path)
    requested_max_cameras = args.max_cameras or DEFAULT_MAX_CAMERAS
    if args.repeat_cameras:
        base_config = _expand_config_repeating_cameras(base_config, requested_max_cameras)
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

    max_cameras = min(requested_max_cameras, len(logical))
    if max_cameras < 1:
        raise SystemExit("--max-cameras должен быть больше нуля")

    out_dir = (repo_root / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "base_config": str(base_path.relative_to(repo_root)),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "max_cameras": max_cameras,
        "modes": ["thread", "process"],
        "repeat_cameras": bool(args.repeat_cameras),
        "shared_detector_pool": bool(args.shared_detector_pool),
        "detector_process_only": bool(args.detector_process_only),
        "capture_process_also": capture_process_also,
        "runs": [],
        "missing_video_paths": missing,
        "notes": [
            "Конфиги сгенерированы автоматически для A/B сравнения thread/process.",
            "Для честного сравнения не меняйте видео, модель и параметры FPS между режимами.",
            "При shared_detector_pool объединённые детекторы применяются и к thread, и к process.",
            *(
                ["При capture_process_also в process-конфигах sources и detectors в process, остальное в thread."]
                if capture_process_also
                else []
            ),
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
                shared_detector_pool=args.shared_detector_pool,
                detector_process_only=args.detector_process_only,
                capture_process_also=capture_process_also,
            )
            _normalize_local_file_references(generated, base_path.parent, repo_root)
            _normalize_detection_threads(generated, args.num_detection_threads)
            _normalize_target_fps(generated, args.target_fps)
            filename = f"bench_{cameras:02d}cam_{mode}.json"
            config_path = out_dir / filename
            _write_json(config_path, generated)
            manifest["runs"].append(
                {
                    "camera_count": cameras,
                    "mode": mode,
                    "config": _path_for_manifest(config_path, repo_root),
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
    parser.add_argument(
        "--repeat-cameras",
        action="store_true",
        help="Повторять доступные видеоисточники с новыми source_ids, если в base-config меньше камер чем --max-cameras.",
    )
    parser.add_argument(
        "--num-detection-threads",
        type=int,
        default=None,
        help="Переопределить num_detection_threads во всех detector-конфигах для воспроизводимого benchmark.",
    )
    parser.add_argument(
        "--shared-detector-pool",
        action="store_true",
        help="Объединять совместимые detector entries в один multi-source detector (thread и process) для одной модели на все камеры.",
    )
    parser.add_argument(
        "--detector-process-only",
        action="store_true",
        help="В process-конфигах запускать detectors в process-mode; остальные стадии по умолчанию в thread-mode. С --capture-process-also — также sources (захват) в process.",
    )
    parser.add_argument(
        "--capture-process-also",
        action="store_true",
        help="Только с --detector-process-only: в process-конфигах вынести в отдельные процессы и источники (захват). Трекеры и прочее остаются в thread.",
    )
    parser.add_argument(
        "--capture-and-detector-process-only",
        action="store_true",
        help="Сокращение: то же, что --detector-process-only --capture-process-also (захват и детектор в process, остальное в thread).",
    )
    parser.add_argument(
        "--target-fps",
        type=float,
        default=None,
        help="Переопределить desired_fps источников, FPS visualizer-а и controller.fps.",
    )
    args = parser.parse_args()
    if args.capture_and_detector_process_only:
        args.detector_process_only = True
        args.capture_process_also = True

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
