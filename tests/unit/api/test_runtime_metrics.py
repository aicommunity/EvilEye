"""Prometheus export of pipeline runtime telemetry."""
from __future__ import annotations

from evileye.api.core.runtime_metrics import metric_names, render_prometheus

STATS = {
    "published_at": 1234.5,
    "degraded": True,
    "modules": {},
    "module_instances": {
        "detectors:0:yolo": {
            "module_id": "yolo",
            "execution_mode": "process",
            "degraded": True,
            "input_queue_dropped": 3,
            "item_errors": 2,
            "worker_restarts": 1,
            "in_flight": 4,
            "error_policy": "skip_item",
        },
        'detectors:1:we"ird\nid': {"degraded": False, "input_queue_dropped": 0},
    },
    "stages": {
        "detectors": {
            "degraded": False,
            "detector_fanout_incomplete": 5,
            "detector_fanout_recent_incomplete": 0,
            "pending_detector_fanout": 2,
            "detector_fanout_policy": "forward_partial",
            "class_space": {"remapped_detectors": [1]},
        }
    },
}


def test_render_prometheus_exports_counters_and_gauges():
    text = render_prometheus(STATS)

    assert "# TYPE evileye_degraded gauge\nevileye_degraded 1" in text
    assert "# TYPE evileye_module_input_queue_dropped_total counter" in text
    assert 'evileye_module_input_queue_dropped_total{module="detectors:0:yolo"} 3' in text
    assert 'evileye_module_item_errors_total{module="detectors:0:yolo"} 2' in text
    assert 'evileye_module_worker_restarts_total{module="detectors:0:yolo"} 1' in text
    assert 'evileye_module_degraded{module="detectors:0:yolo"} 1' in text
    assert 'evileye_module_in_flight{module="detectors:0:yolo"} 4' in text
    assert 'evileye_stage_detector_fanout_incomplete_total{stage="detectors"} 5' in text
    assert 'evileye_stage_detector_fanout_recent_incomplete{stage="detectors"} 0' in text
    assert "evileye_telemetry_published_timestamp_seconds 1234.5" in text


def test_render_prometheus_skips_non_numeric_values_and_escapes_labels():
    text = render_prometheus(STATS)

    assert "execution_mode" not in text and "error_policy" not in text and "class_space" not in text
    assert 'module="detectors:1:we\\"ird\\nid"' in text
    assert text.endswith("\n")
    names = list(metric_names(text))
    assert len(set(names)) == len(names)  # each metric family is declared once


def test_render_prometheus_handles_empty_snapshot():
    assert render_prometheus({}) == "\n"


def test_metrics_route_returns_prometheus_text(monkeypatch):
    import asyncio

    from evileye.api.routes import system

    async def fake_stats(_request):
        return STATS

    monkeypatch.setattr(system, "_runtime_stats", fake_stats)

    response = asyncio.run(system.system_metrics(object()))

    assert response.media_type.startswith("text/plain")
    assert b"evileye_module_item_errors_total" in response.body


def test_metrics_path_needs_runtime_view_permission():
    from evileye.api.security import required_permissions_for_request

    assert required_permissions_for_request("/api/v1/system/metrics", "GET") == {"runtime:view"}
