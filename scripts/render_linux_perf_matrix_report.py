#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
from typing import Any

import render_multiprocessing_benchmark_report as mp_report


PRIMARY_METRIC = {
    "capture": ("visual_fps_est", "Визуализация, кадры/с"),
    "detection": ("detector_fps_est", "Обнаружение, кадры/с"),
    "tracking": ("tracker_fps_est", "Отслеживание, кадры/с"),
    "visualization": ("visual_fps_est", "Визуализация, кадры/с"),
    "full": ("detector_fps_est", "Обнаружение, кадры/с"),
}

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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _fmt(value: Any, digits: int = 2) -> str:
    parsed = _safe_float(value)
    if parsed is None:
        return "-"
    return f"{parsed:.{digits}f}".replace(".", ",")


def _resource_ok(row: dict[str, Any], args: argparse.Namespace) -> bool:
    cpu = _safe_float(row.get("avg_cpu_percent"))
    gpu = _safe_float(row.get("avg_gpu_util_percent"))
    ram = _safe_float(row.get("max_ram_gb"))
    if args.max_cpu_percent is not None and cpu is not None and cpu >= args.max_cpu_percent:
        return False
    if args.max_gpu_percent is not None and gpu is not None and gpu >= args.max_gpu_percent:
        return False
    if args.max_ram_gb is not None and ram is not None and ram >= args.max_ram_gb:
        return False
    return True


def _normalize_device(device: str) -> tuple[str, str]:
    if device == "cuda_0":
        return "cuda:0", "GPU"
    if device == "cuda:0":
        return "cuda:0", "GPU"
    return device, device.upper()


def _parse_results_csv_file(
    csv_path: Path,
    *,
    device: str,
    device_label: str,
    scenario: str,
    scenario_label: str,
    layout: str,
    layout_label: str,
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    metric_name, metric_label = PRIMARY_METRIC.get(scenario, ("detector_fps_est", "Обнаружение, кадры/с"))
    with csv_path.open("r", encoding="utf-8-sig", newline="") as inp:
        reader = csv.DictReader(inp, delimiter=";")
        for item in reader:
            mode_label = str(item.get("Режим", ""))
            mode = "process" if "Мультипроцесс" in mode_label else "thread"
            row: dict[str, Any] = {
                "device": device,
                "device_label": device_label,
                "scenario": scenario,
                "scenario_label": scenario_label,
                "layout": layout,
                "layout_label": layout_label,
                "camera_count": int(item.get("Количество камер") or 0),
                "mode": mode,
                "mode_label": mode_label,
                "avg_capture_fps": _safe_float(item.get("Захват, кадры/с")),
                "detector_fps_est": _safe_float(item.get("Обнаружение, кадры/с")),
                "tracker_fps_est": _safe_float(item.get("Отслеживание, кадры/с")),
                "visual_fps_est": _safe_float(item.get("Визуализация, кадры/с")),
                "p95_pipeline_ms": _safe_float(item.get("p95 цикла, мс")),
                "avg_cpu_percent": _safe_float(item.get("CPU, %")),
                "max_ram_gb": _safe_float(item.get("RAM, ГБ")),
                "avg_gpu_util_percent": _safe_float(item.get("GPU, %")),
                "max_gpu_ram_gb": _safe_float(item.get("GPU-RAM, ГБ")),
                "errors": int(item.get("Ошибки") or 0),
                "valid_run": item.get("Валидный прогон") == "да",
                "timed_out": item.get("Таймаут") == "да",
                "exit_code": item.get("Код выхода"),
                "primary_metric": metric_name,
                "primary_metric_label": metric_label,
                "source_results_csv": str(csv_path),
            }
            row["primary_fps"] = row.get(metric_name)
            row["resource_ok"] = _resource_ok(row, args)
            row["valid_for_report"] = bool(row.get("valid_run")) and bool(row["resource_ok"])
            rows.append(row)
    mp_report._fix_mp_capture_outliers(rows)
    return rows


def _sort_matrix_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("device")),
            str(row.get("scenario")),
            str(row.get("layout")),
            int(row.get("camera_count") or 0),
            str(row.get("mode")),
        ),
    )


def _extend_matrix_row(item: dict[str, Any], row: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    scenario = str(item["scenario"])
    metric_name, metric_label = PRIMARY_METRIC.get(scenario, ("detector_fps_est", "Обнаружение, кадры/с"))
    extended = {
        **item,
        **row,
        "primary_metric": metric_name,
        "primary_metric_label": metric_label,
        "primary_fps": row.get(metric_name),
    }
    extended["primary_fps"] = extended.get(metric_name)
    extended["resource_ok"] = _resource_ok(extended, args)
    extended["valid_for_report"] = bool(extended.get("valid_run")) and bool(extended["resource_ok"])
    return extended


def _collect_matrix_rows(matrix: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    repo_root = _repo_root()
    rows: list[dict[str, Any]] = []
    for item in matrix.get("runs", []):
        out_dir = repo_root / str(item["result_dir"])
        if not out_dir.exists():
            continue
        run_rows = mp_report.collect_rows(out_dir, warmup_windows=args.warmup_windows)
        if not run_rows:
            csv_path = out_dir / "results.csv"
            if csv_path.exists():
                run_rows = _parse_results_csv_file(
                    csv_path,
                    device=str(item["device"]),
                    device_label=str(item.get("device_label", item["device"])),
                    scenario=str(item["scenario"]),
                    scenario_label=str(item.get("scenario_label", SCENARIO_LABELS.get(str(item["scenario"]), item["scenario"]))),
                    layout=str(item["layout"]),
                    layout_label=str(item.get("layout_label", LAYOUT_LABELS.get(str(item["layout"]), item["layout"]))),
                    args=args,
                )
        batch: list[dict[str, Any]] = []
        for row in run_rows:
            if row.get("device"):
                batch.append(row)
            else:
                batch.append(_extend_matrix_row(item, row, args))
        mp_report._fix_mp_capture_outliers(batch)
        rows.extend(batch)
    return _sort_matrix_rows(rows)


def _collect_results_csv_rows(results_root: Path, args: argparse.Namespace) -> list[dict[str, Any]]:
    """Fallback for copied/partial artifacts where logs are absent but results.csv exists."""
    rows: list[dict[str, Any]] = []
    for csv_path in sorted(results_root.rglob("results.csv")):
        try:
            relative = csv_path.relative_to(results_root)
            device_raw, scenario, layout = relative.parts[:3]
        except (ValueError, IndexError):
            continue
        device, device_label = _normalize_device(device_raw)
        rows.extend(
            _parse_results_csv_file(
                csv_path,
                device=device,
                device_label=device_label,
                scenario=scenario,
                scenario_label=SCENARIO_LABELS.get(scenario, scenario),
                layout=layout,
                layout_label=LAYOUT_LABELS.get(layout, layout),
                args=args,
            )
        )
    return _sort_matrix_rows(rows)


def _write_summary_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "Устройство",
        "Сценарий",
        "Схема multiprocessing",
        "Количество камер",
        "Режим",
        "Основная метрика",
        "Основная метрика, кадры/с",
        "Захват, кадры/с",
        "Обнаружение, кадры/с",
        "Отслеживание, кадры/с",
        "Визуализация, кадры/с",
        "p95 цикла, мс",
        "CPU, %",
        "RAM, ГБ",
        "GPU, %",
        "GPU-RAM, ГБ",
        "Ошибки",
        "Валидный прогон",
        "Ресурсы в пределах",
        "Можно использовать в отчете",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "Устройство": row.get("device_label", row.get("device")),
                    "Сценарий": row.get("scenario_label", row.get("scenario")),
                    "Схема multiprocessing": row.get("layout_label", row.get("layout")),
                    "Количество камер": row.get("camera_count"),
                    "Режим": row.get("mode_label"),
                    "Основная метрика": row.get("primary_metric_label"),
                    "Основная метрика, кадры/с": _fmt(row.get("primary_fps")),
                    "Захват, кадры/с": _fmt(row.get("avg_capture_fps")),
                    "Обнаружение, кадры/с": _fmt(row.get("detector_fps_est")),
                    "Отслеживание, кадры/с": _fmt(row.get("tracker_fps_est")),
                    "Визуализация, кадры/с": _fmt(row.get("visual_fps_est")),
                    "p95 цикла, мс": _fmt(row.get("p95_pipeline_ms")),
                    "CPU, %": _fmt(row.get("avg_cpu_percent")),
                    "RAM, ГБ": _fmt(row.get("max_ram_gb")),
                    "GPU, %": _fmt(row.get("avg_gpu_util_percent")),
                    "GPU-RAM, ГБ": _fmt(row.get("max_gpu_ram_gb")),
                    "Ошибки": row.get("errors", 0),
                    "Валидный прогон": "да" if row.get("valid_run") else "нет",
                    "Ресурсы в пределах": "да" if row.get("resource_ok") else "нет",
                    "Можно использовать в отчете": "да" if row.get("valid_for_report") else "нет",
                }
            )


def _speedup_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str, str, int], dict[str, dict[str, Any]]] = {}
    for row in rows:
        key = (
            str(row.get("device")),
            str(row.get("scenario")),
            str(row.get("layout")),
            int(row.get("camera_count") or 0),
        )
        by_key.setdefault(key, {})[str(row.get("mode"))] = row

    result: list[dict[str, Any]] = []
    for key, pair in by_key.items():
        thread = pair.get("thread")
        process = pair.get("process")
        if not thread or not process:
            continue
        thread_fps = _safe_float(thread.get("primary_fps"))
        process_fps = _safe_float(process.get("primary_fps"))
        thread_p95 = _safe_float(thread.get("p95_pipeline_ms"))
        process_p95 = _safe_float(process.get("p95_pipeline_ms"))
        result.append(
            {
                "device": key[0],
                "device_label": process.get("device_label", key[0]),
                "scenario": key[1],
                "scenario_label": process.get("scenario_label", key[1]),
                "layout": key[2],
                "layout_label": process.get("layout_label", key[2]),
                "camera_count": key[3],
                "primary_metric_label": process.get("primary_metric_label"),
                "thread_fps": thread_fps,
                "process_fps": process_fps,
                "speedup": (process_fps / thread_fps) if thread_fps and process_fps else None,
                "p95_delta_percent": ((thread_p95 - process_p95) / thread_p95 * 100.0)
                if thread_p95 and process_p95
                else None,
                "valid_for_report": bool(thread.get("valid_for_report")) and bool(process.get("valid_for_report")),
            }
        )
    return sorted(result, key=lambda row: (row["device"], row["scenario"], row["layout"], row["camera_count"]))


def _write_speedup_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "Устройство",
        "Сценарий",
        "Схема multiprocessing",
        "Количество камер",
        "Основная метрика",
        "Однопроцессный, кадры/с",
        "Мультипроцессный, кадры/с",
        "Ускорение",
        "Снижение p95 задержки, %",
        "Можно использовать в отчете",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "Устройство": row.get("device_label"),
                    "Сценарий": row.get("scenario_label"),
                    "Схема multiprocessing": row.get("layout_label"),
                    "Количество камер": row.get("camera_count"),
                    "Основная метрика": row.get("primary_metric_label"),
                    "Однопроцессный, кадры/с": _fmt(row.get("thread_fps")),
                    "Мультипроцессный, кадры/с": _fmt(row.get("process_fps")),
                    "Ускорение": _fmt(row.get("speedup")),
                    "Снижение p95 задержки, %": _fmt(row.get("p95_delta_percent")),
                    "Можно использовать в отчете": "да" if row.get("valid_for_report") else "нет",
                }
            )


def _write_speedup_plots(rows: list[dict[str, Any]], plots_dir: Path) -> list[Path]:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except ImportError:
        return []

    plots_dir.mkdir(parents=True, exist_ok=True)
    for stale in plots_dir.glob("speedup_*.png"):
        stale.unlink()
    created: list[Path] = []
    groups = sorted({(row["device"], row["scenario"], row["layout"]) for row in rows})
    for device, scenario, layout in groups:
        group_rows = sorted(
            [row for row in rows if (row["device"], row["scenario"], row["layout"]) == (device, scenario, layout)],
            key=lambda row: int(row["camera_count"]),
        )
        cameras = [int(row["camera_count"]) for row in group_rows]
        speedups = [0.0 if _safe_float(row.get("speedup")) is None else float(row["speedup"]) for row in group_rows]
        if not cameras or all(value <= 0 for value in speedups):
            continue
        title = f"Ускорение: {group_rows[0]['device_label']}"
        fig, ax = plt.subplots(figsize=(8.5, 4.8))
        ax.plot(cameras, speedups, marker="o")
        ax.axhline(1.0, color="gray", linestyle="--", linewidth=1)
        ax.set_title(title)
        ax.set_xlabel("Количество камер")
        ax.set_ylabel("Ускорение, раз")
        ax.set_xticks(cameras)
        ax.grid(alpha=0.25)
        fig.tight_layout()
        filename = f"speedup_{device}_{scenario}_{layout}.png".replace(":", "_")
        path = plots_dir / filename
        fig.savefig(path, dpi=160)
        plt.close(fig)
        created.append(path)
    return created


def render(args: argparse.Namespace) -> None:
    repo_root = _repo_root()
    matrix_path = (repo_root / args.matrix_manifest).resolve()
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    out_dir = (repo_root / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = _collect_matrix_rows(matrix, args)
    if not rows:
        results_root = repo_root / str(matrix.get("results_root", "reports/linux_perf_matrix/results"))
        rows = _collect_results_csv_rows(results_root, args)
    if not rows:
        raise SystemExit("Не найдены результаты матрицы. Сначала выполните scripts/run_linux_perf_matrix.sh.")

    speedups = _speedup_rows(rows)
    _write_summary_csv(rows, out_dir / "summary.csv")
    _write_speedup_csv(speedups, out_dir / "speedup.csv")
    _write_speedup_plots(speedups, out_dir / "plots")
    print(f"CSV: {(out_dir / 'summary.csv').relative_to(repo_root)}")
    print(f"Ускорения: {(out_dir / 'speedup.csv').relative_to(repo_root)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Собрать сводный отчет по Linux performance matrix.")
    parser.add_argument("--matrix-manifest", default="reports/linux_perf_matrix/configs/matrix_manifest.json")
    parser.add_argument("--out-dir", default="reports/linux_perf_matrix/summary")
    parser.add_argument("--warmup-windows", type=int, default=1)
    parser.add_argument("--max-cpu-percent", type=float, default=(os.cpu_count() or 1) * 90.0)
    parser.add_argument("--max-gpu-percent", type=float, default=95.0)
    parser.add_argument("--max-ram-gb", type=float, default=None)
    args = parser.parse_args()
    render(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
