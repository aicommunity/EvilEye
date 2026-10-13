"""Pure, side-effect-free pipeline topology descriptions and renderers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping


@dataclass(frozen=True)
class PipelineNode:
    node_id: str
    label: str
    kind: str
    stage: str
    module_id: str | None = None
    status: str = "configured"
    detail: str = ""


@dataclass(frozen=True)
class PipelineEdge:
    source: str
    target: str
    label: str = ""


@dataclass(frozen=True)
class PipelineTopology:
    pipeline_id: str
    title: str
    nodes: tuple[PipelineNode, ...]
    edges: tuple[PipelineEdge, ...]
    description: str = ""
    telemetry_published_at: float | None = None
    telemetry_age_seconds: float | None = None
    telemetry_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": 1,
            "pipeline_id": self.pipeline_id,
            "title": self.title,
            "description": self.description,
            "nodes": [asdict(node) for node in self.nodes],
            "edges": [asdict(edge) for edge in self.edges],
        }
        if self.telemetry_status is not None:
            result["telemetry"] = {
                "status": self.telemetry_status,
                "published_at": self.telemetry_published_at,
                "age_seconds": self.telemetry_age_seconds,
            }
        return result

    def with_runtime(self, snapshot: Mapping[str, Any] | None, *, now: float | None = None,
                     stale_after_sec: float = 15.0) -> "PipelineTopology":
        """Merge already-published module health; never initialize runtime objects."""
        import time
        import math

        current = time.time() if now is None else now
        telemetry = snapshot.get("runtime_telemetry") if isinstance(snapshot, Mapping) else None
        stamp = None
        module_stats: Mapping[str, Any] = {}
        stage_stats: Mapping[str, Any] = {}
        if isinstance(telemetry, Mapping):
            try:
                stamp = float(telemetry.get("published_at"))
                if not math.isfinite(stamp):
                    stamp = None
            except (TypeError, ValueError):
                stamp = None
            instance_stats = telemetry.get("module_instances")
            legacy_stats = telemetry.get("modules")
            if isinstance(legacy_stats, Mapping):
                module_stats = dict(legacy_stats)
            else:
                module_stats = {}
            if isinstance(instance_stats, Mapping):
                # Per-instance keys are authoritative for pipeline processors;
                # event detectors still publish through the legacy map.
                module_stats.update(instance_stats)
            stage_stats = telemetry.get("stages") if isinstance(telemetry.get("stages"), Mapping) else {}
        has_telemetry = isinstance(telemetry, Mapping) and stamp is not None
        fresh = has_telemetry and current - stamp <= stale_after_sec and stamp <= current + 5
        runtime_state = snapshot.get("state") if isinstance(snapshot, Mapping) else None
        live = runtime_state == "running"
        merged: list[PipelineNode] = []
        for node in self.nodes:
            if node.status == "disabled":
                merged.append(node)
                continue
            if node.detail == "module is not registered":
                merged.append(replace(node, status="unknown"))
                continue
            stage_stat = _find_stage_stats(stage_stats, node)
            if node.module_id is None:
                if not has_telemetry:
                    status = "unknown"
                elif not fresh or runtime_state in {"stopped", "dead", "failed"}:
                    status = "stale"
                elif not live:
                    status = "unknown"
                elif isinstance(stage_stat, Mapping) and bool(stage_stat.get("degraded")):
                    status = "degraded"
                elif isinstance(stage_stat, Mapping) and bool(stage_stat.get("unknown_modules")):
                    status = "unknown"
                else:
                    status = "running"
                merged.append(replace(node, status=status))
                continue
            stat = _find_module_stats(module_stats, node, nodes=self.nodes)
            if not has_telemetry:
                status = "unknown"
            elif not fresh or runtime_state in {"stopped", "dead", "failed"}:
                status = "stale"
            elif not live:
                status = "unknown"
            elif (
                isinstance(stage_stat, Mapping) and bool(stage_stat.get("degraded"))
            ):
                status = "degraded"
            elif not isinstance(stat, Mapping):
                status = "unknown"
            elif stat.get("state") == "unknown":
                status = "unknown"
            elif bool(stat.get("degraded")) or stat.get("state") == "degraded":
                status = "degraded"
            elif stat.get("state") in {"failed", "dead", "error"}:
                status = "degraded"
            elif stat.get("state") in {"stale", "stopped", "stopping", "finished"}:
                status = "stale"
            elif stat.get("state") is not None and stat.get("state") not in {"running", "healthy", "ready"}:
                status = "unknown"
            elif stat.get("last_error"):
                status = "degraded"
            elif stat.get("initialized") is False or stat.get("module_initialized") is False:
                status = "degraded"
            elif stat.get("started") is False:
                status = "degraded"
            elif any(
                stat.get(key) is not None and stat.get(key) == 0
                for key in ("worker_running", "backend_worker_running")
            ) and not stat.get("finished"):
                status = "degraded"
            elif not any(
                key in stat
                for key in (
                    "state", "worker_running", "backend_worker_running", "started",
                    "initialized", "module_initialized",
                )
            ):
                status = "unknown"
            else:
                status = "running"
            merged.append(replace(node, status=status))
        return replace(
            self, nodes=tuple(merged), telemetry_published_at=stamp,
            telemetry_age_seconds=max(0.0, current - stamp) if stamp is not None else None,
            telemetry_status="fresh" if fresh else "stale" if has_telemetry else "unknown",
        )


def _find_module_stats(
    stats: Mapping[str, Any], node: PipelineNode, *, nodes: tuple[PipelineNode, ...] = ()
) -> Mapping[str, Any] | None:
    from evileye.core.plugins import plugin_registry

    exact = stats.get(node.node_id)
    if isinstance(exact, Mapping):
        return exact

    # Older snapshots used "stage/module_id" keys. They cannot distinguish
    # duplicate modules, so only apply that legacy match when it is unambiguous.
    module_id = node.module_id or ""
    if not module_id:
        return None
    registered = plugin_registry.get_module(module_id)
    qualified_id = registered.qualified_id if registered is not None else module_id
    aliases = set((module_id, qualified_id))
    if registered is not None:
        aliases.update(registered.spec.legacy_ids)
    # Runtime adapters expose qualified IDs even when the original config
    # uses a legacy type. Match that same instance before any aggregate key.
    if node.node_id.endswith(module_id):
        prefix = node.node_id[:-len(module_id)]
        for alias in aliases:
            value = stats.get(prefix + alias)
            if isinstance(value, Mapping):
                return value
    def canonical(identity):
        item = plugin_registry.get_module(identity or "")
        return item.qualified_id if item is not None else identity
    same_module_count = sum(
        canonical(candidate.module_id) == qualified_id and candidate.stage == node.stage
        for candidate in nodes
    )
    if same_module_count > 1:
        return None
    stage_key = node.node_id.split(":", 1)[0]
    if stage_key == "stage":
        stage_key = node.stage
    for alias in aliases:
        legacy = stats.get(f"{stage_key}/{alias}")
        if isinstance(legacy, Mapping):
            return legacy
    # Some pre-release snapshots used a qualified key with a different stage
    # prefix. Preserve only a unique suffix match for those snapshots.
    matches = [
        value for key, value in stats.items()
        if any(str(key).endswith("/" + alias) for alias in aliases) and isinstance(value, Mapping)
    ]
    return matches[0] if len(matches) == 1 else None


def _find_stage_stats(stats: Mapping[str, Any], node: PipelineNode) -> Mapping[str, Any] | None:
    stage_key = node.node_id.split(":", 1)[0]
    if stage_key in {group for group, _, _, _ in _SURVEILLANCE_STAGES}:
        value = stats.get(stage_key)
        return value if isinstance(value, Mapping) else None
    if stage_key in {"events", "pipeline"}:
        value = stats.get(stage_key)
        return value if isinstance(value, Mapping) else None
    value = stats.get(node.stage) or stats.get(node.stage.lower())
    return value if isinstance(value, Mapping) else None


_SURVEILLANCE_STAGES = (
    ("sources", "Sources", "source", "VideoCaptureOpencv"),
    ("preprocessors", "Preprocessors", "preprocessor", "PreprocessingPipeline"),
    ("detectors", "Detectors", "detector", "ObjectDetectorYolo"),
    ("trackers", "Trackers", "tracker", "ObjectTrackingBotsort"),
    ("mc_trackers", "Multi-camera trackers", "batch_processor", "ObjectMultiCameraTracking"),
    ("attributes_roi", "ROI attributes", "attribute", "RoiFeeder"),
    ("attributes_classifier", "Attribute classifiers", "attribute", "AttributeClassifier"),
)


def _pipeline_root(config: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = config.get("pipeline")
    return nested if isinstance(nested, Mapping) else config


def _module_id(item: Any, default: str) -> str:
    if not isinstance(item, Mapping):
        return default
    return str(item.get("module_id") or item.get("type") or default)


def _group_items(pipeline: Mapping[str, Any], group: str) -> list[Any]:
    original = list(pipeline.get(group) or []) if isinstance(pipeline.get(group), list) else []
    extensions = pipeline.get("modules") or {}
    extension = extensions.get(group) if isinstance(extensions, Mapping) else None
    if isinstance(extension, Mapping):
        items = extension.get("items")
        if isinstance(items, list):
            mode = str(extension.get("mode") or "").lower()
            if mode == "replace":
                return list(items)
            if mode == "extend":
                return [*original, *items]
    return original


def _item_label(item: Any, module_id: str, index: int) -> str:
    if isinstance(item, Mapping):
        names = item.get("source_names")
        if isinstance(names, (list, tuple)) and names:
            name = ", ".join(str(value) for value in names)
        else:
            name = item.get("display_name") or item.get("name") or _module_display_name(module_id)
        return str(name) + f" [{index + 1}]"
    return f"{_module_display_name(module_id)} [{index + 1}]"


def _module_display_name(module_id: str) -> str:
    from evileye.core.plugins import plugin_registry

    registered = plugin_registry.get_module(module_id)
    if registered is not None and registered.spec.display_name:
        return str(registered.spec.display_name)
    return module_id


def _add_events(root: Mapping[str, Any], nodes: list[PipelineNode], edges: list[PipelineEdge], upstream: list[str]) -> None:
    event_cfg = root.get("events_detectors")
    from evileye.events_detectors.event_registry import DEFAULT_ENABLED_EVENT_DETECTORS

    if not isinstance(event_cfg, Mapping):
        event_cfg = {}
    configured = {
        str(key): value for key, value in event_cfg.items()
        if key != "enabled"
    }
    enabled_value = event_cfg.get("enabled")
    enabled_names = (
        {str(value) for value in enabled_value}
        if isinstance(enabled_value, list)
        else set(DEFAULT_ENABLED_EVENT_DETECTORS)
    )
    active_names = (
        [str(value) for value in enabled_value]
        if isinstance(enabled_value, list)
        else list(DEFAULT_ENABLED_EVENT_DETECTORS)
    )
    event_names = list(dict.fromkeys([
        *active_names,
        *configured.keys(),
    ]))
    if not event_names:
        return
    branch = "events:branch"
    nodes.append(PipelineNode(branch, "Event and alarm rules", "event_branch", "Events"))
    for source in upstream:
        edges.append(PipelineEdge(source, branch, "events / objects"))
    for index, configured_id in enumerate(event_names):
        item = configured.get(configured_id, {})
        if not isinstance(item, Mapping):
            item = {}
        module_id = str(item.get("module_id") or configured_id)
        node_id = f"events:{index}:{module_id}"
        enabled = configured_id in enabled_names
        nodes.append(PipelineNode(
            node_id, f"{_module_display_name(module_id)} [{index + 1}]", "event_detector", "Events",
            module_id=module_id, status="configured" if enabled else "disabled",
        ))
        edges.append(PipelineEdge(branch, node_id, "alarm rules"))


def build_surveillance_topology(config: Mapping[str, Any]) -> PipelineTopology:
    root = config if isinstance(config, Mapping) else {}
    pipeline = _pipeline_root(root)
    nodes: list[PipelineNode] = []
    edges: list[PipelineEdge] = []
    previous: list[tuple[str, Any]] = []
    previous_stage_name = ""
    event_upstream: list[str] = []
    for group, stage_label, kind, default in _SURVEILLANCE_STAGES:
        group_nodes: list[tuple[str, Any]] = []
        for index, item in enumerate(_group_items(pipeline, group)):
            module_id = _module_id(item, default)
            node_id = f"{group}:{index}:{module_id}"
            enabled = not isinstance(item, Mapping) or bool(item.get("enable", item.get("enabled", True)))
            nodes.append(PipelineNode(
                node_id, _item_label(item, module_id, index), kind, stage_label,
                module_id=module_id,
                status="configured" if enabled else "disabled",
            ))
            group_nodes.append((node_id, item))
        if previous and group_nodes:
            for source_id, source_item in previous:
                source_ids = _source_ids(source_item)
                for target_id, target_item in group_nodes:
                    target_ids = _source_ids(target_item)
                    if not source_ids or not target_ids or source_ids.intersection(target_ids):
                        edges.append(PipelineEdge(source_id, target_id, previous_stage_name))
        elif previous and not group_nodes:
            pass
        if group_nodes:
            if not previous:
                # First stage is allowed to have no incoming edges.
                pass
            previous = group_nodes
            previous_stage_name = stage_label
            active_nodes = [
                node_id for node_id, item in group_nodes
                if not isinstance(item, Mapping)
                or bool(item.get("enable", item.get("enabled", True)))
            ]
            if active_nodes:
                event_upstream = active_nodes
    _add_events(root, nodes, edges, event_upstream)
    pipeline_id = str(pipeline.get("pipeline_class") or "PipelineSurveillance")
    return PipelineTopology(pipeline_id, "PipelineSurveillance", tuple(nodes), _unique_edges(edges),
                            "Frame stages are ordered; event detectors run on a separate branch.")


def _source_ids(item: Any) -> set[str]:
    if not isinstance(item, Mapping):
        return set()
    values = item.get("source_ids")
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {str(value) for value in values}


def declarative_stage_configs(pipeline: Mapping[str, Any]) -> list[Any]:
    """Return the explicit stages or the supported legacy section shorthand."""
    stages = pipeline.get("stages")
    if stages:
        if not isinstance(stages, list):
            raise ValueError("pipeline.stages must be an array")
        return stages
    return [
            {"name": name, "kind": kind, "items": pipeline.get(name) or []}
            for name, kind in (
                ("sources", "source"),
                ("preprocessors", "frame"),
                ("detectors", "step"),
                ("trackers", "step"),
                ("mc_trackers", "step"),
                ("attributes_roi", "step"),
                ("attributes_classifier", "step"),
            )
            if isinstance(pipeline.get(name), list) and pipeline.get(name)
    ]


def build_declarative_topology(config: Mapping[str, Any]) -> PipelineTopology:
    root = config if isinstance(config, Mapping) else {}
    pipeline = _pipeline_root(root)
    nodes: list[PipelineNode] = []
    edges: list[PipelineEdge] = []
    previous: list[str] = []
    event_upstream: list[str] = []
    for stage_index, stage in enumerate(declarative_stage_configs(pipeline)):
        if not isinstance(stage, Mapping):
            continue
        stage_name = str(stage.get("name") or f"stage_{stage_index}")
        kind = str(stage.get("kind") or "step")
        members: list[str] = []
        active_members: list[str] = []
        for index, item in enumerate(stage.get("items") or []):
            module_id = _module_id(item, {"source": "VideoCaptureOpencv", "frame": "PreprocessingPipeline", "step": "ObjectDetectorYolo"}.get(kind, "ObjectDetectorYolo"))
            node_id = f"stage:{stage_index}:{index}:{module_id}"
            enabled = not isinstance(item, Mapping) or bool(item.get("enable", item.get("enabled", True)))
            nodes.append(PipelineNode(node_id, _item_label(item, module_id, index), kind, stage_name,
                                      module_id, "configured" if enabled else "disabled"))
            members.append(node_id)
            if enabled:
                active_members.append(node_id)
            for source_id in previous:
                edges.append(PipelineEdge(source_id, node_id, stage_name))
        if members:
            previous = members
        if active_members:
            event_upstream = active_members
    _add_events(root, nodes, edges, event_upstream)
    return PipelineTopology(str(pipeline.get("pipeline_class") or "PipelineDeclarative"),
                            "PipelineDeclarative", tuple(nodes), _unique_edges(edges),
                            "Declarative stages execute in the configured order.")


def build_capture_topology(config: Mapping[str, Any]) -> PipelineTopology:
    """Describe the simple capture pipeline without opening its video source."""
    root = config if isinstance(config, Mapping) else {}
    pipeline = _pipeline_root(root)
    nodes: list[PipelineNode] = []
    # PipelineCapture constructs one OpenCV source from sources[0]; it does
    # not execute the Surveillance module-group overrides or other factories.
    sources = pipeline.get("sources")
    sources = sources if isinstance(sources, list) else []
    for index, item in enumerate(sources[:1]):
        module_id = "VideoCaptureOpencv"
        enabled = not isinstance(item, Mapping) or bool(item.get("enable", item.get("enabled", True)))
        nodes.append(PipelineNode(
            node_id=f"sources:{index}:{module_id}",
            label=_item_label(item, module_id, index),
            kind="source",
            stage="Sources",
            module_id=module_id,
            status="configured" if enabled else "disabled",
        ))
    pipeline_id = str(pipeline.get("pipeline_class") or "PipelineCapture")
    return PipelineTopology(
        pipeline_id,
        "Capture pipeline",
        tuple(nodes),
        (),
        "This pipeline captures a video file through its first OpenCV source; additional sources are not executed.",
    )


def build_opaque_topology(config: Mapping[str, Any], pipeline_id: str, *, display_name: str | None = None,
                          description: str = "") -> PipelineTopology:
    node = PipelineNode("pipeline", display_name or pipeline_id, "pipeline", "Pipeline", module_id=None)
    notice = "Internal topology is not declared by this pipeline plugin."
    return PipelineTopology(pipeline_id, display_name or pipeline_id, (node,), (),
                            f"{description} {notice}".strip())


def build_topology(config: Mapping[str, Any], *, pipeline_id: str | None = None) -> PipelineTopology:
    """Resolve a declared pipeline topology without constructing its implementation."""
    from evileye.core.builtin_inventory import register_builtins
    from evileye.core.plugins import plugin_registry

    root = config if isinstance(config, Mapping) else {}
    pipeline = _pipeline_root(root)
    selected = pipeline_id or str(pipeline.get("pipeline_class") or "PipelineSurveillance")
    register_builtins()
    registered = plugin_registry.get_pipeline(selected)
    if registered is None:
        return build_opaque_topology(root, selected, description="Pipeline is not registered; no internal topology is available.")
    provider = registered.spec.topology_provider
    if callable(provider):
        result = provider(root)
        if not isinstance(result, PipelineTopology):
            raise TypeError(f"Topology provider for '{registered.qualified_id}' must return PipelineTopology")
        return _mark_unregistered_modules(result, plugin_registry)
    return build_opaque_topology(root, registered.qualified_id, display_name=registered.spec.display_name,
                                 description=registered.spec.description or "")


def _mark_unregistered_modules(topology: PipelineTopology, registry: Any) -> PipelineTopology:
    unknown: list[str] = []
    nodes: list[PipelineNode] = []
    for node in topology.nodes:
        if node.module_id and registry.get_module(node.module_id) is None:
            unknown.append(node.module_id)
            nodes.append(replace(node, status="unknown", detail="module is not registered"))
        else:
            nodes.append(node)
    if not unknown:
        return topology
    warning = "Unregistered modules: " + ", ".join(dict.fromkeys(unknown))
    description = f"{topology.description} {warning}".strip()
    return replace(topology, nodes=tuple(nodes), description=description)


def _unique_edges(edges: list[PipelineEdge]) -> tuple[PipelineEdge, ...]:
    seen: set[tuple[str, str, str]] = set()
    result: list[PipelineEdge] = []
    for edge in edges:
        key = (edge.source, edge.target, edge.label)
        if key not in seen:
            seen.add(key)
            result.append(edge)
    return tuple(result)


def render_tree(topology: PipelineTopology):
    from rich.tree import Tree
    from rich.markup import escape

    root = Tree(f"[bold]{escape(topology.title)}[/bold] [dim]({escape(topology.pipeline_id)})[/dim]")
    stages: dict[str, Any] = {}
    for node in topology.nodes:
        stage = stages.get(node.stage)
        if stage is None:
            stage = root.add(f"[cyan]{escape(node.stage)}[/cyan]")
            stages[node.stage] = stage
        status_style = {"running": "green", "configured": "white", "degraded": "red", "stale": "yellow", "unknown": "dim", "disabled": "dim"}.get(node.status, "white")
        label = f"{escape(node.label)} {escape('[' + node.status + ']')}"
        stage.add(f"[{status_style}]{label}[/{status_style}]")
    if topology.description:
        root.add(f"[dim]{escape(topology.description)}[/dim]")
    if topology.telemetry_status is not None:
        root.add(f"[dim]{_telemetry_label(topology)}[/dim]")
    return root


def render_edges(topology: PipelineTopology):
    from rich.table import Table
    from rich.markup import escape

    names = {node.node_id: f"{escape(node.stage)}: {escape(node.label)}" for node in topology.nodes}
    table = Table(title=f"{escape(topology.title)} connections")
    table.add_column("From")
    table.add_column("To")
    table.add_column("Path")
    table.add_column("Status")
    if topology.telemetry_status is not None:
        table.caption = _telemetry_label(topology)
    states = {node.node_id: node.status for node in topology.nodes}
    for edge in _unique_edges(list(topology.edges)):
        table.add_row(names.get(edge.source, escape(edge.source)), names.get(edge.target, escape(edge.target)), escape(edge.label),
                      escape(f"{states.get(edge.source, 'unknown')} → {states.get(edge.target, 'unknown')}"))
    if not topology.edges:
        table.add_row("—", "—", escape(topology.description or "No declared connections"), "—")
    return table


def _telemetry_label(topology: PipelineTopology) -> str:
    age = f" · age={topology.telemetry_age_seconds:.1f}s" if topology.telemetry_age_seconds is not None else ""
    return f"Telemetry: {topology.telemetry_status}{age}"


def render_dot(topology: PipelineTopology) -> str:
    def quote(value: str) -> str:
        return ('"' + str(value).replace("\\", "\\\\").replace('"', '\\"')
                .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + '"')

    lines = ["digraph pipeline {", "  rankdir=LR;", "  node [shape=box];"]
    if topology.telemetry_status is not None:
        lines.append(f"  label={quote(_telemetry_label(topology))};")
    for node in topology.nodes:
        label = f"{node.stage}\n{node.label}\n[{node.status}]"
        lines.append(f"  {quote(node.node_id)} [label={quote(label)}];")
    for edge in _unique_edges(list(topology.edges)):
        label = f" [label={quote(edge.label)}]" if edge.label else ""
        lines.append(f"  {quote(edge.source)} -> {quote(edge.target)}{label};")
    lines.append("}")
    return "\n".join(lines)
