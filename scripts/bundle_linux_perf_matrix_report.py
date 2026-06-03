#!/usr/bin/env python3
"""Собрать таблицы и графики матрицы benchmark в один каталог для отчёта."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

PLOT_FILES = (
    "capture_fps.png",
    "detection_fps.png",
    "tracking_fps.png",
    "visualization_fps.png",
    "cpu_percent.png",
    "ram_gb.png",
    "gpu_percent.png",
    "gpu_ram_gb.png",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_slug(*parts: str) -> str:
    return "__".join(
        part.replace(":", "_").replace("/", "_").replace(" ", "_") for part in parts if part
    )


def bundle(args: argparse.Namespace) -> None:
    repo_root = _repo_root()
    matrix_path = (repo_root / args.matrix_manifest).resolve()
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    bundle_dir = (repo_root / args.bundle_dir).resolve()
    summary_dir = (repo_root / args.summary_dir).resolve()

    if bundle_dir.exists() and args.clean:
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    for name in ("summary.csv", "speedup.csv", "report.md"):
        src = summary_dir / name
        if src.exists():
            shutil.copy2(src, bundle_dir / name)

    plots_src = summary_dir / "plots"
    if plots_src.exists():
        plots_dst = bundle_dir / "summary_plots"
        if plots_dst.exists():
            shutil.rmtree(plots_dst)
        shutil.copytree(plots_src, plots_dst)

    tables_dir = bundle_dir / "tables"
    plots_dir = bundle_dir / "plots"
    tables_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for item in matrix.get("runs", []):
        result_dir = repo_root / str(item["result_dir"])
        if not result_dir.exists():
            continue
        slug = _safe_slug(
            str(item.get("device", "")),
            str(item.get("scenario", "")),
            str(item.get("layout", "")),
        )
        results_csv = result_dir / "results.csv"
        if results_csv.exists():
            shutil.copy2(results_csv, tables_dir / f"{slug}_results.csv")

        run_plots = result_dir / "plots"
        if not run_plots.exists():
            continue
        run_plot_dst = plots_dir / slug
        run_plot_dst.mkdir(parents=True, exist_ok=True)
        for plot_name in PLOT_FILES:
            src_plot = run_plots / plot_name
            if src_plot.exists():
                shutil.copy2(src_plot, run_plot_dst / plot_name)
                copied += 1

    readme_lines = [
        "# Каталог результатов benchmark",
        "",
        f"Манифест матрицы: `{matrix_path.relative_to(repo_root).as_posix()}`",
        "",
        "## Содержимое",
        "",
        "- `summary.csv`, `speedup.csv`, `report.md` — сводка по всей матрице.",
        "- `summary_plots/` — графики ускорения из сводного renderer-а (если построены).",
        "- `tables/*_results.csv` — таблицы по каждой группе (устройство × сценарий × layout).",
        "- `plots/<группа>/` — графики FPS и ресурсов для группы.",
        "",
        "## Группы в этой итерации",
        "",
    ]
    for item in matrix.get("runs", []):
        readme_lines.append(
            f"- `{item.get('device_label', item.get('device'))}` / "
            f"`{item.get('scenario_label', item.get('scenario'))}` / "
            f"`{item.get('layout_label', item.get('layout'))}` → "
            f"`{item.get('result_dir')}`"
        )
    readme_lines.extend(
        [
            "",
            f"Скопировано файлов графиков: {copied}.",
            "",
            "Подробная методика: `docs/diploma_benchmark_methodology.md`.",
        ]
    )
    (bundle_dir / "README.md").write_text("\n".join(readme_lines) + "\n", encoding="utf-8")
    print(f"Каталог отчёта: {bundle_dir.relative_to(repo_root)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Собрать артефакты матрицы benchmark в один каталог.")
    parser.add_argument("--matrix-manifest", required=True)
    parser.add_argument("--results-root", default="")
    parser.add_argument("--summary-dir", required=True)
    parser.add_argument("--bundle-dir", required=True)
    parser.add_argument("--warmup-windows", type=int, default=1)
    parser.add_argument("--clean", action="store_true", default=True)
    args = parser.parse_args()
    bundle(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
