"""Render pipeline runtime telemetry in the Prometheus text exposition format."""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

# Monotonic counters; everything else numeric is exported as a gauge.
_COUNTER_FIELDS = frozenset({
    "input_queue_dropped",
    "input_queue_rejected",
    "item_errors",
    "worker_restarts",
    "detector_fanout_incomplete",
    "detector_fanout_dropped",
    "detector_fanout_empty_responses",
})
_SKIPPED_FIELDS = frozenset({"published_at"})
_NAME_RE = re.compile(r"[^a-zA-Z0-9_]")


def _metric_name(prefix: str, field: str) -> str:
    name = _NAME_RE.sub("_", f"{prefix}_{field}").strip("_")
    if field in _COUNTER_FIELDS and not name.endswith("_total"):
        name += "_total"
    return name


def _escape(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)) and value == value and value not in (float("inf"), float("-inf")):
        return float(value)
    return None


def _collect(prefix: str, scope: str, items: Mapping[str, Any], label: str, out: dict) -> None:
    for identity, stats in items.items():
        if not isinstance(stats, Mapping):
            continue
        for field, value in stats.items():
            if field in _SKIPPED_FIELDS:
                continue
            number = _numeric(value)
            if number is None:
                continue
            name = _metric_name(prefix, field)
            kind = "counter" if field in _COUNTER_FIELDS else "gauge"
            entry = out.setdefault(name, {"type": kind, "samples": []})
            entry["samples"].append(({label: identity}, number))


def render_prometheus(stats: Mapping[str, Any]) -> str:
    """Convert a ``Controller._collect_runtime_telemetry`` snapshot to Prometheus text."""
    metrics: dict[str, dict[str, Any]] = {}
    _collect("evileye_module", "module", dict(stats.get("module_instances") or stats.get("modules") or {}), "module", metrics)
    _collect("evileye_stage", "stage", dict(stats.get("stages") or {}), "stage", metrics)
    overall = _numeric(stats.get("degraded"))
    if overall is not None:
        metrics.setdefault("evileye_degraded", {"type": "gauge", "samples": []})["samples"].append(({}, overall))
    published = _numeric(stats.get("published_at"))
    if published is not None:
        metrics.setdefault("evileye_telemetry_published_timestamp_seconds", {"type": "gauge", "samples": []})[
            "samples"
        ].append(({}, published))

    lines: list[str] = []
    for name in sorted(metrics):
        entry = metrics[name]
        lines.append(f"# TYPE {name} {entry['type']}")
        for labels, value in entry["samples"]:
            rendered = ",".join(f'{key}="{_escape(val)}"' for key, val in labels.items())
            lines.append(f"{name}{{{rendered}}} {value:g}" if rendered else f"{name} {value:g}")
    return "\n".join(lines) + "\n"


def metric_names(text: str) -> Iterable[str]:
    return [line.split()[2] for line in text.splitlines() if line.startswith("# TYPE ")]
