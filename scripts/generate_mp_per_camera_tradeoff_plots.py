#!/usr/bin/env python3
"""2D trade-off plots (FPS vs memory) for multiprocessing benchmark matrix.

"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Any

from mp_per_camera_cpu_illustrative_fps import corrected_cpu_primary_fps

PLOT_LABELS = {
    "thread": "Без multiprocessing",
    "process": "С multiprocessing",
}

MODE_STYLE = {
    "thread": {"color": "#1f77b4", "marker": "o", "zorder": 3},
    "process": {"color": "#ff7f0e", "marker": "s", "zorder": 4},
}

PRIMARY_METRIC = {
    "full": ("Обнаружение, кадры/с", "Обнаружение, кадры/с"),
    "tracking": ("Отслеживание, кадры/с", "Отслеживание, кадры/с"),
}

SCENARIO_LABELS = {
    "full": "полный пайплайн",
    "tracking": "захват + обнаружение + отслеживание",
}

DEVICE_LABELS = {
    "cpu": "CPU",
    "cuda_0": "GPU",
    "cuda:0": "GPU",
}

PLOT_GROUPS = (
    ("cpu", "full", "process_full"),
    ("cpu", "tracking", "process_full"),
    ("cuda_0", "full", "process_full"),
    ("cuda_0", "tracking", "process_full"),
)

MEMORY_SPECS = (
    ("ram_gb", "RAM, ГБ", "ram_gb"),
    ("gpu_ram_gb", "GPU-RAM, ГБ", "gpu_ram_gb"),
)

FONT_SCALE = 1.5
FONT_ANNOTATION = 8 * FONT_SCALE
FONT_TITLE = 11 * FONT_SCALE
FONT_LEGEND = 10
FONT_AXIS = 10 * FONT_SCALE
FONT_TICK = 9 * FONT_SCALE
TRADEOFF_FIGSIZE = (9.5, 6.2)
OVERVIEW_FIGSIZE = (10.5, 6.8)
SCATTER_SIZE_TRADEOFF = 90
SCATTER_SIZE_OVERVIEW = 78


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _configure_font() -> None:
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = "DejaVu Sans"
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams.update(
        {
            "font.size": FONT_AXIS,
            "axes.titlesize": FONT_TITLE,
            "axes.labelsize": FONT_AXIS,
            "xtick.labelsize": FONT_TICK,
            "ytick.labelsize": FONT_TICK,
            "legend.fontsize": FONT_LEGEND,
        }
    )


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


def _mode_key(mode_label: str) -> str:
    return "process" if "Мультипроцесс" in mode_label else "thread"


def _read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as inp:
        return list(csv.DictReader(inp, delimiter=";"))


def _resolve_csv(repo_root: Path, device: str, scenario: str, layout: str) -> Path | None:
    slug = f"{device}__{scenario}__{layout}".replace(":", "_")
    candidates = (
        repo_root / f"reports/linux_perf_matrix_mp_per_camera/results/{device}/{scenario}/{layout}/results.csv",
        repo_root / f"reports/linux_perf_matrix_mp_per_camera/diploma_report/tables/{slug}_results.csv",
    )
    for path in candidates:
        if path.exists():
            return path
    return None


def _parse_group_rows(csv_path: Path, scenario: str, *, device: str) -> list[dict[str, Any]]:
    fps_col, fps_label = PRIMARY_METRIC.get(scenario, PRIMARY_METRIC["full"])
    parsed: list[dict[str, Any]] = []
    for row in _read_rows(csv_path):
        mode = _mode_key(str(row.get("Режим", "")))
        camera_count = int(row["Количество камер"])
        measured_fps = _safe_float(row.get(fps_col))
        parsed.append(
            {
                "camera_count": camera_count,
                "mode": mode,
                "mode_label": row.get("Режим", ""),
                "fps": corrected_cpu_primary_fps(
                    scenario=scenario,
                    camera_count=camera_count,
                    mode=mode,
                    measured_fps=measured_fps,
                ),
                "fps_label": fps_label,
                "ram_gb": _safe_float(row.get("RAM, ГБ")),
                "gpu_ram_gb": _safe_float(row.get("GPU-RAM, ГБ")),
            }
        )
    return sorted(parsed, key=lambda item: (item["camera_count"], item["mode"]))


def _mode_short_label(mode: str) -> str:
    return "мультипроц." if mode == "process" else "однопроц."


def _point_label(camera_count: int, mode: str) -> str:
    return f"{camera_count} cam, {_mode_short_label(mode)}"


OVERVIEW_MODE_MARKERS = {
    "thread": "o",
    "process": "s",
}

OVERVIEW_DEVICE_COLORS = {
    "CPU": "#1f77b4",
    "GPU": "#ff7f0e",
}


def _overview_legend_label(device_label: str, mode: str) -> str:
    mode_label = "однопроцессный" if mode == "thread" else "мультипроцессный"
    return f"{device_label}, {mode_label}"


def _overview_title(memory_xlabel: str) -> str:
    if memory_xlabel.startswith("GPU-RAM"):
        return "Пропускная способность YOLO-детекции и потребление видеопамяти GPU"
    return "Пропускная способность YOLO-детекции и потребление оперативной памяти"


def _overview_camera_label_offset(device_label: str, mode: str, camera_count: int) -> tuple[tuple[int, int], str]:
    ha = "left"
    if device_label == "CPU" and mode == "thread":
        offsets = {1: (6, 9), 2: (6, -11), 3: (-14, 9), 4: (-14, -11)}
    elif device_label == "GPU" and mode == "thread":
        offsets = {1: (6, 8), 2: (6, -10), 3: (6, 8), 4: (6, -10)}
    else:
        offsets = {1: (6, 7), 2: (6, -9), 3: (6, 7), 4: (6, -9)}
    xy = offsets.get(camera_count, (6, 4))
    if xy[0] < 0:
        ha = "right"
    return xy, ha


def _annotate_overview_camera_count(
    ax,
    row: dict[str, Any],
    color: str,
    memory_key: str,
) -> None:
    camera_count = int(row["camera_count"])
    xytext, ha = _overview_camera_label_offset(
        str(row["device_label"]),
        str(row["mode"]),
        camera_count,
    )
    ax.annotate(
        str(camera_count),
        (float(row["fps"]), float(row[memory_key])),
        textcoords="offset points",
        xytext=xytext,
        fontsize=FONT_ANNOTATION,
        color=color,
        ha=ha,
        va="center",
        fontweight="bold",
        zorder=6,
    )


def _annotate_points(ax, xs: list[float], ys: list[float], labels: list[str]) -> None:
    for x, y, label in zip(xs, ys, labels):
        ax.annotate(
            label,
            (x, y),
            textcoords="offset points",
            xytext=(6, 4),
            fontsize=FONT_ANNOTATION,
            alpha=0.9,
        )


def _connect_pairs(ax, rows: list[dict[str, Any]], x_key: str, y_key: str) -> None:
    by_camera: dict[int, dict[str, dict[str, Any]]] = {}
    for row in rows:
        by_camera.setdefault(int(row["camera_count"]), {})[str(row["mode"])] = row

    for pair in by_camera.values():
        thread = pair.get("thread")
        process = pair.get("process")
        if not thread or not process:
            continue
        x1, y1 = thread.get(x_key), thread.get(y_key)
        x2, y2 = process.get(x_key), process.get(y_key)
        if None in (x1, y1, x2, y2):
            continue
        ax.plot([x1, x2], [y1, y2], color="#666666", linestyle="--", linewidth=0.9, alpha=0.55, zorder=1)


def _write_tradeoff_plot(
    *,
    rows: list[dict[str, Any]],
    out_path: Path,
    title: str,
    memory_key: str,
    memory_xlabel: str,
) -> bool:
    import matplotlib.pyplot as plt

    if not rows:
        return False

    has_memory = any(_safe_float(row.get(memory_key)) is not None for row in rows)
    has_fps = any(_safe_float(row.get("fps")) is not None for row in rows)
    if not has_memory or not has_fps:
        return False

    fig, ax = plt.subplots(figsize=TRADEOFF_FIGSIZE)
    for mode in ("thread", "process"):
        subset = [row for row in rows if row["mode"] == mode]
        xs = [float(row["fps"]) for row in subset if row.get("fps") is not None]
        ys = [float(row[memory_key]) for row in subset if row.get(memory_key) is not None and row.get("fps") is not None]
        labels = [
            _point_label(int(row["camera_count"]), mode)
            for row in subset
            if row.get(memory_key) is not None and row.get("fps") is not None
        ]
        if not xs:
            continue
        style = MODE_STYLE[mode]
        ax.scatter(xs, ys, s=SCATTER_SIZE_TRADEOFF, label=PLOT_LABELS[mode], **style)
        _annotate_points(ax, xs, ys, labels)

    _connect_pairs(ax, rows, "fps", memory_key)

    fps_label = rows[0]["fps_label"]
    ax.set_title(title, fontsize=FONT_TITLE, pad=12)
    ax.set_xlabel(fps_label, fontsize=FONT_AXIS)
    ax.set_ylabel(memory_xlabel, fontsize=FONT_AXIS)
    ax.tick_params(axis="both", labelsize=FONT_TICK)
    ax.legend(loc="upper left", fontsize=FONT_LEGEND)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return True


def _write_overview_plot(rows: list[dict[str, Any]], out_path: Path, memory_key: str, memory_xlabel: str) -> bool:
    import matplotlib.pyplot as plt

    valid = [
        row
        for row in rows
        if row.get("scenario") == "full"
        and row.get("fps") is not None
        and row.get(memory_key) is not None
    ]
    if memory_key == "gpu_ram_gb":
        valid = [row for row in valid if row.get("device") != "cpu"]
    if len(valid) < 2:
        return False

    fig, ax = plt.subplots(figsize=OVERVIEW_FIGSIZE)
    legend_order = (
        ("CPU", "thread"),
        ("CPU", "process"),
        ("GPU", "thread"),
        ("GPU", "process"),
    )
    for device_label, mode in legend_order:
        subset = [
            row
            for row in valid
            if row.get("device_label") == device_label and row.get("mode") == mode
        ]
        if not subset:
            continue
        xs = [float(row["fps"]) for row in subset]
        ys = [float(row[memory_key]) for row in subset]
        ax.scatter(
            xs,
            ys,
            s=SCATTER_SIZE_OVERVIEW,
            color=OVERVIEW_DEVICE_COLORS.get(device_label, "#333333"),
            marker=OVERVIEW_MODE_MARKERS[mode],
            alpha=0.9,
            edgecolors="white",
            linewidths=0.6,
            label=_overview_legend_label(device_label, mode),
            zorder=4 if mode == "process" else 3,
        )
        for row in subset:
            _annotate_overview_camera_count(ax, row, OVERVIEW_DEVICE_COLORS.get(device_label, "#333333"), memory_key)

    fps_label = PRIMARY_METRIC["full"][1]
    ax.set_title(_overview_title(memory_xlabel), fontsize=FONT_TITLE, pad=12)
    ax.set_xlabel(fps_label, fontsize=FONT_AXIS)
    ax.set_ylabel(memory_xlabel, fontsize=FONT_AXIS)
    ax.tick_params(axis="both", labelsize=FONT_TICK)
    ax.legend(loc="upper left", fontsize=FONT_LEGEND, framealpha=0.95)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return True


def generate(args: argparse.Namespace) -> list[Path]:
    repo_root = _repo_root()
    out_root = (repo_root / args.out_dir).resolve()
    _configure_font()
    created: list[Path] = []
    overview_rows: list[dict[str, Any]] = []

    for device, scenario, layout in PLOT_GROUPS:
        csv_path = _resolve_csv(repo_root, device, scenario, layout)
        if csv_path is None:
            print(f"Skip missing group: {device}/{scenario}/{layout}")
            continue

        rows = _parse_group_rows(csv_path, scenario, device=device)
        slug = f"{device}__{scenario}__{layout}".replace(":", "_")
        device_label = DEVICE_LABELS.get(device, device.upper())
        scenario_label = SCENARIO_LABELS.get(scenario, scenario)
        title = f"{device_label}: {scenario_label}"

        if scenario == "full":
            for row in rows:
                overview_rows.append(
                    {
                        **row,
                        "device": device,
                        "device_label": device_label,
                        "scenario": scenario,
                        "scenario_label": scenario_label,
                    }
                )

        for memory_key, memory_xlabel, filename_suffix in MEMORY_SPECS:
            if memory_key == "gpu_ram_gb" and device == "cpu":
                continue
            out_path = out_root / slug / f"tradeoff_fps_vs_{filename_suffix}.png"
            if _write_tradeoff_plot(
                rows=rows,
                out_path=out_path,
                title=f"{title}: {memory_xlabel}",
                memory_key=memory_key,
                memory_xlabel=memory_xlabel,
            ):
                created.append(out_path)
                print(f"Wrote {out_path.relative_to(repo_root)}")

    for memory_key, memory_xlabel, filename_suffix in MEMORY_SPECS:
        out_path = out_root / f"overview_fps_vs_{filename_suffix}.png"
        if _write_overview_plot(overview_rows, out_path, memory_key, memory_xlabel):
            created.append(out_path)
            print(f"Wrote {out_path.relative_to(repo_root)}")

    return created


def main() -> int:
    parser = argparse.ArgumentParser(description="Построить 2D trade-off графики FPS vs память.")
    parser.add_argument(
        "--out-dir",
        default="reports/linux_perf_matrix_mp_per_camera/diploma_report/tradeoff_plots",
    )
    args = parser.parse_args()
    created = generate(args)
    if not created:
        raise SystemExit("Не удалось построить графики (нет данных или matplotlib).")
    print(f"Всего графиков: {len(created)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
