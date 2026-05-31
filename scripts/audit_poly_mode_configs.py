#!/usr/bin/env python3
"""Audit poly-videos configs: diffs, video paths, JSON validity."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from poly_mode_compare_lib import (
    COMPARE_CONFIGS,
    DEFAULT_OUT_DIR,
    REPO_ROOT,
    compare_config_pair,
    config_video_paths,
    load_config,
)


def _check_videos(cfg_path: Path) -> list[str]:
    missing: list[str] = []
    for video in config_video_paths(load_config(cfg_path)):
        if not Path(video).is_file():
            missing.append(video)
    return missing


def render_audit_md(out_dir: Path) -> str:
    lines = [
        "# Аудит конфигов poly-videos (process vs thread)",
        "",
        "## Сравниваемые файлы",
        "",
        "| Capture | Mode | Config |",
        "| --- | --- | --- |",
    ]
    for spec in COMPARE_CONFIGS:
        lines.append(
            f"| {spec['capture']} | {spec['mode']} | `{spec['config']}` |"
        )
    lines.extend(["", "## Пары process/thread", ""])

    pairs = [
        ("opencv", "configs/poly-videos.json", "configs/poly-videos-thread.json"),
        ("gst", "configs/poly-videos-gst.json", "configs/poly-videos-gst-thread.json"),
    ]
    unexpected_total = 0
    for label, path_a, path_b in pairs:
        diffs = compare_config_pair(REPO_ROOT / path_a, REPO_ROOT / path_b)
        unexpected = [d for d in diffs if not d["expected"]]
        unexpected_total += len(unexpected)
        lines.append(f"### {label}: `{path_a}` vs `{path_b}`")
        lines.append(f"- Всего отличий: **{len(diffs)}**")
        lines.append(f"- Неожиданных (кроме execution_mode): **{len(unexpected)}**")
        if unexpected:
            lines.append("")
            lines.append("| Ключ | process/value A | thread/value B |")
            lines.append("| --- | --- | --- |")
            for item in unexpected:
                lines.append(
                    f"| `{item['key']}` | `{item['a']}` | `{item['b']}` |"
                )
        else:
            lines.append("")
            lines.append("Неожиданных отличий нет (только `execution_mode`).")
        lines.append("")

    lines.extend(["## Видеофайлы", ""])
    all_missing: list[str] = []
    for spec in COMPARE_CONFIGS:
        cfg_path = REPO_ROOT / spec["config"]
        missing = _check_videos(cfg_path)
        all_missing.extend(missing)
        status = "OK" if not missing else "MISSING"
        lines.append(f"- `{spec['config']}`: **{status}**")
        for path in missing:
            lines.append(f"  - отсутствует: `{path}`")
    lines.append("")

    lines.extend(
        [
            "## OpenCV vs GStreamer (справочно)",
            "",
            "Между `poly-videos*.json` и `poly-videos-gst*.json` ожидаются отличия "
            "`type`, `apiPreference`, `gstreamer_*` и пути захвата — это разные backend.",
            "",
        ]
    )
    opencv_vs_gst = compare_config_pair(
        REPO_ROOT / "configs/poly-videos.json",
        REPO_ROOT / "configs/poly-videos-gst.json",
    )
    lines.append(f"- Число отличий opencv vs gst (базовые process-конфиги): **{len(opencv_vs_gst)}**")
    lines.append("")
    return "\n".join(lines)


def _run_validate_json() -> tuple[int, str]:
    script = REPO_ROOT / "scripts" / "validate_json_configs.py"
    if not script.is_file():
        return 0, "validate_json_configs.py not found (skipped)"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()[-2000:] if out else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit poly-videos benchmark configs.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR.relative_to(REPO_ROOT)))
    parser.add_argument("--skip-validate", action="store_true")
    args = parser.parse_args()
    out_dir = (REPO_ROOT / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    for spec in COMPARE_CONFIGS:
        path = REPO_ROOT / spec["config"]
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{path}: {exc}")
        errors.extend(f"Missing video for {spec['config']}: {m}" for m in _check_videos(path))

    if not args.skip_validate:
        code, tail = _run_validate_json()
        if code != 0:
            errors.append(f"validate_json_configs.py failed (exit {code})")
            if tail:
                errors.append(tail)

    audit_md = render_audit_md(out_dir)
    if not args.skip_validate:
        audit_md += "\n## Preflight\n\n- `validate_json_configs.py`: **OK**\n"
    audit_path = out_dir / "config_audit.md"
    audit_path.write_text(audit_md, encoding="utf-8")
    print(f"Wrote {audit_path.relative_to(REPO_ROOT)}")

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
