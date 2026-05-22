#!/usr/bin/env python3
"""Parse poly-videos benchmark logs for MP barrier metrics."""

from __future__ import annotations

import argparse
import ast
import csv
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from poly_mode_compare_lib import COMPARE_CONFIGS, DEFAULT_OUT_DIR, REPO_ROOT

RE_PIPELINE_LOOP = re.compile(r"PerfDiag\(Pipeline\): loop=(\d+)")
RE_DET_LEN0 = re.compile(r"detectors=[0-9.]+ms\(len=0\)")
RE_TRK_LEN0 = re.compile(r"trackers=[0-9.]+ms\(len=0\)")
RE_DETECTORS_IN = re.compile(
    r"PerfDiag\(DetectorsIn\): window=\d+ updates=(\{[^}]+\})"
)
RE_TRACKERS_OUT = re.compile(
    r"PerfDiag\(TrackersOut\): window=\d+ updates=(\{[^}]+\})"
)
RE_MC_STEP = re.compile(
    r"PerfDiag\(MCStep\): tick=\d+ batch_in=(\d+) emitted=(\d+)"
)
RE_DROP = re.compile(
    r"queue is full|dropping detection|Output queue full|Worker init failed",
    re.IGNORECASE,
)
RE_TRACEBACK = re.compile(r"Traceback \(most recent call last\):")
RE_ERROR = re.compile(r"\bERROR\b")


def _sum_updates(match_iter) -> int:
    total = 0
    for m in match_iter:
        try:
            d = ast.literal_eval(m.group(1))
            if isinstance(d, dict):
                total += sum(int(v) for v in d.values())
        except (SyntaxError, ValueError, TypeError):
            pass
    return total


def parse_log_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    pipeline_ticks = len(RE_PIPELINE_LOOP.findall(text))
    det_len0 = len(RE_DET_LEN0.findall(text))
    trk_len0 = len(RE_TRK_LEN0.findall(text))
    detectors_in = _sum_updates(RE_DETECTORS_IN.finditer(text))
    trackers_out = _sum_updates(RE_TRACKERS_OUT.finditer(text))
    mc_batch_in = 0
    mc_emitted = 0
    for m in RE_MC_STEP.finditer(text):
        mc_batch_in += int(m.group(1))
        mc_emitted += int(m.group(2))
    lag_ratio = detectors_in / max(1, trackers_out)
    slug = ""
    mode = ""
    capture = ""
    run_index = 0
    for spec in COMPARE_CONFIGS:
        if spec["slug"] in path.stem:
            slug = spec["slug"]
            mode = spec["mode"]
            capture = spec["capture"]
            break
    m_run = re.search(r"_run(\d+)\.log$", path.name)
    if m_run:
        run_index = int(m_run.group(1))
    return {
        "log_file": str(path.relative_to(REPO_ROOT)),
        "slug": slug,
        "capture": capture,
        "mode": mode,
        "run_index": run_index,
        "pipeline_ticks": pipeline_ticks,
        "pct_det_len0": round(100.0 * det_len0 / max(1, pipeline_ticks), 2),
        "pct_trk_len0": round(100.0 * trk_len0 / max(1, pipeline_ticks), 2),
        "detectors_in_sum": detectors_in,
        "trackers_out_sum": trackers_out,
        "lag_ratio": round(lag_ratio, 3),
        "mc_batch_in_sum": mc_batch_in,
        "mc_emitted_sum": mc_emitted,
        "drop_events": len(RE_DROP.findall(text)),
        "errors": len(RE_ERROR.findall(text)),
        "tracebacks": len(RE_TRACEBACK.findall(text)),
    }


def _aggregate(rows: list[dict[str, Any]], key_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    buckets: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = tuple(row.get(k, "") for k in key_fields)
        buckets[key].append(row)
    out: list[dict[str, Any]] = []
    for key, group in sorted(buckets.items()):
        item = {key_fields[i]: key[i] for i in range(len(key_fields))}
        for metric in (
            "pct_trk_len0",
            "pct_det_len0",
            "lag_ratio",
            "drop_events",
            "pipeline_ticks",
        ):
            vals = [float(g[metric]) for g in group if g.get(metric) is not None]
            if vals:
                item[f"{metric}_mean"] = round(statistics.mean(vals), 3)
                item[f"{metric}_std"] = round(
                    statistics.pstdev(vals) if len(vals) > 1 else 0.0, 3
                )
        item["n"] = len(group)
        out.append(item)
    return out


def render_md(rows: list[dict[str, Any]], agg: list[dict[str, Any]]) -> str:
    lines = [
        "# MP barrier analysis (poly-videos logs)",
        "",
        "## Per-log metrics",
        "",
        "| log | mode | pct_trk_len0 | lag_ratio | drops | tracebacks |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for r in sorted(rows, key=lambda x: (x.get("capture", ""), x.get("mode", ""), x.get("run_index", 0))):
        lines.append(
            f"| `{r['log_file']}` | {r.get('mode', '-')} | {r.get('pct_trk_len0', '-')} | "
            f"{r.get('lag_ratio', '-')} | {r.get('drop_events', 0)} | {r.get('tracebacks', 0)} |"
        )
    lines.extend(["", "## Aggregated by capture + mode", ""])
    lines.append("| capture | mode | n | pct_trk_len0 mean | lag_ratio mean | drops sum |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: |")
    for a in agg:
        drop_sum = sum(
            r["drop_events"]
            for r in rows
            if r.get("capture") == a.get("capture") and r.get("mode") == a.get("mode")
        )
        lines.append(
            f"| {a.get('capture')} | {a.get('mode')} | {a.get('n')} | "
            f"{a.get('pct_trk_len0_mean', '-')} | {a.get('lag_ratio_mean', '-')} | {drop_sum} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- **H2 confirmed** if process `pct_trk_len0_mean` > 50 and `lag_ratio_mean` > 3 vs thread.",
            "- **H3 confirmed** if process `drop_events` > 0 while thread ≈ 0 on same runs.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze MP barriers in poly-videos logs.")
    parser.add_argument("--log-dir", default=str(DEFAULT_OUT_DIR / "logs"))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR.relative_to(REPO_ROOT)))
    parser.add_argument("--slug-filter", default="")
    args = parser.parse_args()

    log_dir = (REPO_ROOT / args.log_dir).resolve()
    out_dir = (REPO_ROOT / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for path in sorted(log_dir.glob("*_run*.log")):
        if "warmup" in path.name:
            continue
        if args.slug_filter and args.slug_filter not in path.name:
            continue
        rows.append(parse_log_file(path))

    if not rows:
        print("No run logs found.", file=__import__("sys").stderr)
        return 1

    fieldnames = list(rows[0].keys())
    csv_path = out_dir / "barrier_metrics.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)

    agg = _aggregate(rows, ("capture", "mode"))
    md_path = out_dir / "barrier_analysis.md"
    md_path.write_text(render_md(rows, agg), encoding="utf-8")
    print(f"Wrote {csv_path.relative_to(REPO_ROOT)}")
    print(f"Wrote {md_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
