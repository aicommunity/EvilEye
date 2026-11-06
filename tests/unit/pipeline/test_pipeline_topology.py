from evileye.core.pipeline_topology import (
    PipelineEdge,
    PipelineNode,
    PipelineTopology,
    build_declarative_topology,
    build_capture_topology,
    build_opaque_topology,
    build_surveillance_topology,
    render_dot,
    render_edges,
    render_tree,
)


def test_surveillance_topology_fans_out_and_keeps_event_rules_separate():
    topology = build_surveillance_topology({
        "pipeline": {
            "pipeline_class": "PipelineSurveillance",
            "sources": [{"source_ids": [0]}, {"source_ids": [1]}],
            "detectors": [{"source_ids": [0]}, {"source_ids": [0]}, {"source_ids": [1]}],
            "trackers": [{"source_ids": [0, 1]}],
            "modules": {"detectors": {"mode": "extend", "items": [{"source_ids": [1]}]}},
            "mc_trackers": [{"enable": False}],
        },
        "events_detectors": {"safety/alarm": {"enabled": True}},
    })

    sources = [node for node in topology.nodes if node.stage == "Sources"]
    detectors = [node for node in topology.nodes if node.stage == "Detectors"]
    assert len(sources) == 2
    assert len(detectors) == 4
    # The second source fans out to its configured detectors; the first source
    # has two parallel detector nodes.
    detector_edges = [edge for edge in topology.edges if edge.target.startswith("detectors:")]
    assert len(detector_edges) == 4
    assert any(node.status == "disabled" for node in topology.nodes)
    assert any(node.kind == "event_detector" for node in topology.nodes)
    event_branch = next(node for node in topology.nodes if node.kind == "event_branch")
    assert not any(edge.target == event_branch.node_id for edge in detector_edges)
    incoming = [edge.source for edge in topology.edges if edge.target == event_branch.node_id]
    assert incoming == ["trackers:0:ObjectTrackingBotsort"]


def test_event_topology_uses_root_enabled_list_and_skips_control_key():
    topology = build_surveillance_topology({
        "pipeline": {"trackers": [{"source_ids": [0]}],
                     "mc_trackers": [{"enable": False, "source_ids": [0]}]},
        "events_detectors": {
            "enabled": ["CamEventsDetector"],
            "CamEventsDetector": {},
            "vendor/safety-rule": {},
        },
    })
    event_nodes = [node for node in topology.nodes if node.kind == "event_detector"]
    assert [(node.module_id, node.status) for node in event_nodes] == [
        ("CamEventsDetector", "configured"),
        ("vendor/safety-rule", "disabled"),
    ]
    assert all(node.module_id != "enabled" for node in topology.nodes)
    branch = next(node for node in topology.nodes if node.kind == "event_branch")
    incoming = [edge.source for edge in topology.edges if edge.target == branch.node_id]
    assert incoming == ["trackers:0:ObjectTrackingBotsort"]


def test_event_topology_shows_default_rules_when_event_section_is_omitted():
    from evileye.events_detectors.event_registry import DEFAULT_ENABLED_EVENT_DETECTORS

    topology = build_surveillance_topology({"pipeline": {}})
    event_nodes = [node for node in topology.nodes if node.kind == "event_detector"]

    assert [node.module_id for node in event_nodes] == list(DEFAULT_ENABLED_EVENT_DETECTORS)
    assert all(node.status == "configured" for node in event_nodes)


def test_surveillance_replace_uses_only_replacement_modules():
    topology = build_surveillance_topology({
        "pipeline": {
            "sources": [{"source_ids": [0]}],
            "detectors": [{"type": "OldDetector", "source_ids": [0]}],
            "modules": {"detectors": {"mode": "replace", "items": [
                {"module_id": "vendor/new-detector", "source_ids": [0]},
            ]}},
        }
    })
    detector_nodes = [node for node in topology.nodes if node.stage == "Detectors"]
    assert [node.module_id for node in detector_nodes] == ["vendor/new-detector"]


def test_declarative_stages_are_ordered_and_form_a_chain():
    topology = build_declarative_topology({"pipeline": {"stages": [
        {"name": "capture", "kind": "source", "items": [{"module_id": "vendor/camera"}]},
        {"name": "rules", "kind": "step", "items": [{"module_id": "vendor/rule"}]},
    ]}})
    stage_nodes = [node for node in topology.nodes if node.stage in {"capture", "rules"}]
    assert [node.stage for node in stage_nodes] == ["capture", "rules"]
    assert any(edge.source == stage_nodes[0].node_id and edge.target == stage_nodes[1].node_id
               for edge in topology.edges)
    assert any(node.kind == "event_branch" for node in topology.nodes)


def test_topology_formats_escape_labels_and_include_statuses():
    topology = PipelineTopology(
        "sample", "Sample",
        (PipelineNode('a";\nattack', 'Camera "one"\nnext', "source", "Sources", "camera", "running"),
         PipelineNode("b", "Alarm", "event_detector", "Events", "alarm", "degraded")),
        (PipelineEdge('a";\nattack', "b", "alarms"), PipelineEdge('a";\nattack', "b", "alarms")),
    )
    dot = render_dot(topology)
    assert dot.startswith("digraph pipeline {")
    assert 'Camera \\"one\\"\\nnext' in dot
    assert 'a\\";\\nattack' in dot
    assert dot.count(" -> ") == 1
    assert "running" in dot and "degraded" in dot
    from io import StringIO
    from rich.console import Console
    capture = StringIO()
    Console(file=capture, force_terminal=False).print(render_tree(topology))
    assert "Camera" in capture.getvalue()
    assert "alarms" in render_edges(topology).columns[2]._cells


def test_rich_renderers_escape_plugin_supplied_markup():
    from io import StringIO
    from rich.console import Console

    topology = PipelineTopology(
        "sample", "[bold red]untrusted title[/bold red]",
        (PipelineNode("source", "camera", "source", "Sources", "camera"),),
        (),
        "[link=https://example.invalid]untrusted description[/link]",
    )
    capture = StringIO()
    Console(file=capture, force_terminal=False).print(render_tree(topology))

    output = capture.getvalue()
    assert "[bold red]untrusted title[/bold red]" in output
    assert "[link=https://example.invalid]untrusted description[/link]" in output

    edges = render_edges(topology)
    edge_capture = StringIO()
    Console(file=edge_capture, force_terminal=False, width=160).print(edges)
    edge_output = edge_capture.getvalue()
    assert "[bold red]untrusted title[/bold red]" in edge_output
    assert "[link=https://example.invalid]untrusted description[/link]" in edge_output


def test_graph_export_omits_camera_credentials_from_configuration():
    import json

    topology = build_surveillance_topology({"pipeline": {"sources": [{
        "camera": "rtsp://operator:do-not-print@camera.local/stream", "source_ids": [0],
    }]}})
    exported = json.dumps(topology.to_dict(), ensure_ascii=False)
    assert "do-not-print" not in exported
    assert "operator" not in exported
    assert "camera.local" not in exported


def test_runtime_status_distinguishes_running_degraded_unknown_and_stale():
    topology = PipelineTopology(
        "sample", "Sample",
        (PipelineNode("sources/Camera", "Camera", "source", "Sources", "Camera"),
         PipelineNode("detectors/Rule", "Rule", "detector", "Detectors", "Rule")),
        (),
    )
    snapshot = {
        "state": "running",
        "runtime_telemetry": {
            "published_at": 1000,
            "modules": {
                "sources/Camera": {"degraded": False, "worker_running": True},
                "detectors/Rule": {"degraded": True, "last_error": "queue full"},
            },
        },
    }
    statuses = [node.status for node in topology.with_runtime(snapshot, now=1001).nodes]
    assert statuses == ["running", "degraded"]
    assert [node.status for node in topology.with_runtime({"state": "running"}, now=1001).nodes] == ["unknown", "unknown"]
    assert [node.status for node in topology.with_runtime({**snapshot, "state": "initialized"}, now=1001).nodes] == ["unknown", "unknown"]
    assert [node.status for node in topology.with_runtime(snapshot, now=1020).nodes] == ["stale", "stale"]


def test_old_runtime_snapshot_does_not_claim_modules_are_healthy():
    topology = build_opaque_topology({}, "vendor/custom")
    updated = topology.with_runtime({"state": "running", "updated_at": 1000}, now=1001)
    assert updated.nodes[0].status == "unknown"


def test_fresh_runtime_snapshot_without_health_signals_stays_unknown():
    topology = PipelineTopology(
        "sample", "Sample",
        (PipelineNode("detectors:0:Rule", "Rule", "detector", "Detectors", "Rule"),),
        (),
    )
    snapshot = {
        "state": "running",
        "runtime_telemetry": {
            "published_at": 1000,
            "module_instances": {"detectors:0:Rule": {"queue_size": 0}},
        },
    }
    assert topology.with_runtime(snapshot, now=1001).nodes[0].status == "unknown"


def test_capture_pipeline_topology_shows_source_without_opening_it():
    topology = build_capture_topology({"pipeline": {
        "pipeline_class": "PipelineCapture",
        "sources": [{"camera": "rtsp://user:password@host/secret", "source_ids": [0]}],
    }})
    assert len(topology.nodes) == 1
    assert topology.nodes[0].module_id == "VideoCaptureOpencv"
    assert topology.nodes[0].stage == "Sources"
    assert "password" not in str(topology.to_dict())


def test_duplicate_modules_use_per_instance_health_and_stage_degradation():
    topology = build_surveillance_topology({"pipeline": {
        "detectors": [
            {"type": "ObjectDetectorYolo", "source_ids": [0]},
            {"type": "ObjectDetectorYolo", "source_ids": [0]},
        ],
    }})
    snapshot = {
        "state": "running",
        "runtime_telemetry": {
            "published_at": 1000,
            "module_instances": {
                "detectors:0:ObjectDetectorYolo": {"worker_running": True},
                "detectors:1:ObjectDetectorYolo": {"degraded": True},
            },
            "stages": {},
        },
    }
    statuses = [
        node.status for node in topology.with_runtime(snapshot, now=1001).nodes
        if node.stage == "Detectors"
    ]
    assert statuses == ["running", "degraded"]

    snapshot["runtime_telemetry"]["module_instances"]["detectors:1:ObjectDetectorYolo"] = {
        "worker_running": True,
    }
    snapshot["runtime_telemetry"]["stages"] = {"detectors": {"degraded": True}}
    statuses = [
        node.status for node in topology.with_runtime(snapshot, now=1001).nodes
        if node.stage == "Detectors"
    ]
    assert statuses == ["degraded", "degraded"]


def test_event_health_is_read_alongside_pipeline_per_instance_telemetry():
    topology = build_surveillance_topology({
        "pipeline": {"detectors": [{"source_ids": [0]}]},
        "events_detectors": {
            "enabled": ["SystemEventsDetector"],
            "SystemEventsDetector": {},
        },
    })
    snapshot = {
        "state": "running",
        "runtime_telemetry": {
            "published_at": 1000,
            "module_instances": {
                "detectors:0:ObjectDetectorYolo": {"worker_running": True},
            },
            "modules": {
                "events/SystemEventsDetector": {"worker_running": True},
            },
        },
    }

    event = next(node for node in topology.with_runtime(snapshot, now=1001).nodes
                 if node.module_id == "SystemEventsDetector")
    assert event.status == "running"


def test_event_branch_and_detectors_reflect_event_stage_degradation():
    topology = build_surveillance_topology({
        "pipeline": {},
        "events_detectors": {"enabled": ["SystemEventsDetector"]},
    })
    snapshot = {
        "state": "running",
        "runtime_telemetry": {
            "published_at": 1000,
            "modules": {"events/SystemEventsDetector": {"worker_running": True}},
            "stages": {"events": {"degraded": True, "last_error": "event queue full"}},
        },
    }

    statuses = {
        node.kind: node.status
        for node in topology.with_runtime(snapshot, now=1001).nodes
        if node.kind in {"event_branch", "event_detector"}
    }
    assert statuses == {"event_branch": "degraded", "event_detector": "degraded"}


def test_synchronous_batch_health_uses_module_initialized_signal():
    topology = PipelineTopology(
        "sample", "Sample",
        (PipelineNode("mc_trackers:0:Batch", "Batch", "batch_processor", "Trackers", "Batch"),),
        (),
    )
    snapshot = {
        "state": "running",
        "runtime_telemetry": {
            "published_at": 1000,
            "module_instances": {"mc_trackers:0:Batch": {"module_initialized": True}},
        },
    }

    assert topology.with_runtime(snapshot, now=1001).nodes[0].status == "running"
    snapshot["runtime_telemetry"]["module_instances"]["mc_trackers:0:Batch"] = {
        "module_initialized": False,
    }
    assert topology.with_runtime(snapshot, now=1001).nodes[0].status == "degraded"


def test_runtime_views_include_telemetry_freshness():
    from io import StringIO
    from rich.console import Console

    topology = build_opaque_topology({}, "vendor/custom")
    snapshot = {"state": "running", "runtime_telemetry": {"published_at": 1000}}
    fresh = topology.with_runtime(snapshot, now=1002)
    assert fresh.to_dict()["telemetry"] == {"status": "fresh", "published_at": 1000, "age_seconds": 2}
    assert topology.with_runtime(snapshot, now=1020).telemetry_status == "stale"
    assert topology.with_runtime({"state": "running"}, now=1002).telemetry_status == "unknown"
    stream = StringIO()
    console = Console(file=stream, force_terminal=False)
    console.print(render_tree(fresh))
    console.print(render_edges(fresh))
    assert stream.getvalue().count("Telemetry: fresh") == 2
    assert "Telemetry: fresh" in render_dot(fresh)


def test_custom_topology_provider_is_used_without_constructing_pipeline():
    import uuid
    from evileye.core.plugins import PluginSpec, PipelineSpec, PLUGIN_API_VERSION, plugin_registry
    from evileye.core.pipeline_topology import build_topology

    def factory(*_args):
        raise AssertionError("inspection must not construct a pipeline")
    plugin_id = "test.topology." + uuid.uuid4().hex
    expected = PipelineTopology(plugin_id + "/custom", "Declared", (), ())
    seen = []
    def provider(config):
        seen.append(config)
        return expected
    plugin_registry.register_plugin(PluginSpec(plugin_id, PLUGIN_API_VERSION, pipelines=(
        PipelineSpec("custom", factory, topology_provider=provider),
    )))
    config = {"pipeline": {"pipeline_class": plugin_id + "/custom"}}
    assert build_topology(config) == expected
    assert seen == [config]


def test_custom_pipeline_without_provider_explicitly_reports_opaque_topology():
    import uuid
    from evileye.core.plugins import PluginSpec, PipelineSpec, PLUGIN_API_VERSION, plugin_registry
    from evileye.core.pipeline_topology import build_topology

    plugin_id = "test.opaque." + uuid.uuid4().hex
    plugin_registry.register_plugin(PluginSpec(plugin_id, PLUGIN_API_VERSION, pipelines=(
        PipelineSpec("custom", dict, description="Vendor analytics"),
    )))
    topology = build_topology({"pipeline": {"pipeline_class": plugin_id + "/custom"}})
    assert len(topology.nodes) == 1
    assert topology.edges == ()
    assert "Vendor analytics" in topology.description
    assert "Internal topology is not declared" in topology.description


def test_legacy_config_ids_match_qualified_runtime_instances_without_merging_health():
    from evileye.core.builtin_inventory import register_builtins

    register_builtins()
    topology = build_surveillance_topology({"pipeline": {"detectors": [
        {"type": "ObjectDetectorYolo"}, {"module_id": "evileye/ObjectDetectorYolo"},
    ]}})
    snapshot = {"state": "running", "runtime_telemetry": {
        "published_at": 1000,
        "module_instances": {
            "detectors:0:evileye/ObjectDetectorYolo": {"worker_running": True},
            "detectors:1:evileye/ObjectDetectorYolo": {"worker_running": True, "degraded": True},
        },
    }}
    statuses = [node.status for node in topology.with_runtime(snapshot, now=1001).nodes if node.stage == "Detectors"]
    assert statuses == ["running", "degraded"]


def test_nonrunning_module_states_and_zero_worker_count_are_not_healthy():
    topology = PipelineTopology("sample", "Sample", (
        PipelineNode("detectors:0:Rule", "Rule", "detector", "Detectors", "Rule"),
    ), ())
    for stats, expected in [
        ({"state": "starting"}, "unknown"),
        ({"state": "failed"}, "degraded"),
        ({"state": "stale"}, "stale"),
        ({"state": "stopped"}, "stale"),
        ({"worker_running": 0}, "degraded"),
        ({"started": False}, "degraded"),
    ]:
        result = topology.with_runtime({"state": "running", "runtime_telemetry": {
            "published_at": 1000, "module_instances": {"detectors:0:Rule": stats},
        }}, now=1001)
        assert result.nodes[0].status == expected, stats
