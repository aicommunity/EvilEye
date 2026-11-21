"""Pipeline topology inspection command shared by CLI and tests."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import typer

from evileye.cli_commands.console import console
from evileye.core.builtin_inventory import register_builtins
from evileye.core.pipeline_topology import (
    PipelineTopology,
    build_topology,
    render_dot,
    render_edges,
    render_tree,
)


def _load_config(path: str) -> tuple[Path, dict[str, Any]]:
    from evileye.utils.config_paths import normalize_config_path

    resolved = Path(normalize_config_path(path)).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Configuration not found: {resolved}")
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Pipeline configuration root must be a JSON object")
    return resolved, data


def _load_run(run_id: int) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    from evileye.api.core.runtime_registry import load_runtime_record, load_runtime_snapshot

    record = load_runtime_record(int(run_id), refresh_state=True)
    if not record:
        raise FileNotFoundError(f"Pipeline run #{run_id} was not found")
    snapshot = load_runtime_snapshot(int(run_id))
    if not snapshot:
        raise FileNotFoundError(f"Pipeline run #{run_id} has no runtime snapshot yet")
    config = snapshot.get("config")
    if not isinstance(config, dict):
        raise ValueError(f"Pipeline run #{run_id} snapshot has no configuration")
    return config, record, snapshot


def _select_config(config: str | None) -> str:
    if config:
        return config
    from evileye.cli_interactive import interactive_available, prompt_config_path

    if interactive_available():
        return prompt_config_path("конфигурация pipeline")
    from evileye.stack_control import require_pipeline_config

    try:
        return require_pipeline_config(Path.cwd(), explicit=None, allow_running=True)
    except Exception as exc:
        raise ValueError(
            "CONFIG is required when no unique site pipeline configuration can be resolved. "
            "Use: evileye pipeline inspect CONFIG"
        ) from exc


def _runtime_topology(config: dict[str, Any], snapshot: dict[str, Any] | None,
                      record: dict[str, Any] | None = None) -> PipelineTopology:
    topology = build_topology(config)
    if snapshot is None:
        return topology
    if isinstance(record, dict) and isinstance(record.get("state"), str):
        # The registry refreshes process liveness when the CLI reads a run. A
        # final snapshot can predate a crash/stop, so the current record state
        # takes precedence over the snapshot's last published state.
        snapshot = {**snapshot, "state": record["state"]}
    return topology.with_runtime(snapshot)


def _render(topology: PipelineTopology, output_format: str, *, run_id: int | None = None,
            snapshot: dict[str, Any] | None = None) -> Any:
    if output_format == "tree":
        return render_tree(topology)
    if output_format == "edges":
        return render_edges(topology)
    if output_format == "dot":
        return render_dot(topology)
    data = topology.to_dict()
    if run_id is not None:
        data["view"] = "runtime"
        data["run_id"] = int(run_id)
        data["snapshot_updated_at"] = snapshot.get("updated_at") if snapshot else None
    else:
        data["view"] = "configuration"
    return json.dumps(data, ensure_ascii=False, indent=2)


def inspect_pipeline(
    config: str | None = typer.Argument(None, help="Pipeline configuration path/name."),
    run: int | None = typer.Option(None, "--run", help="Inspect the saved state of a runtime ID."),
    output_format: str = typer.Option("tree", "--format", help="Output: tree, edges, dot, or json."),
    watch: bool = typer.Option(False, "--watch", help="Refresh a live runtime view until interrupted."),
) -> None:
    """Show declared topology from a config or telemetry from a running process."""
    output_format = output_format.lower()
    if config and run is not None:
        console.print("[red]CONFIG and --run are mutually exclusive.[/red]")
        raise typer.Exit(2)
    if output_format not in {"tree", "edges", "dot", "json"}:
        console.print("[red]--format must be tree, edges, dot, or json.[/red]")
        raise typer.Exit(2)
    if watch and run is None:
        console.print("[red]--watch requires --run ID.[/red]")
        raise typer.Exit(2)
    if watch and output_format in {"dot", "json"}:
        console.print("[red]--watch supports tree and edges output only.[/red]")
        raise typer.Exit(2)
    if watch and not console.is_terminal:
        console.print("[red]--watch requires a terminal (TTY).[/red]")
        raise typer.Exit(2)

    try:
        register_builtins()
        selected_run = run
        if run is not None:
            runtime_config, record, snapshot = _load_run(run)
            config_path = record.get("config_path")
        else:
            selected_path = _select_config(config)
            path, runtime_config = _load_config(selected_path)
            config_path = str(path)
            record = snapshot = None
        topology = _runtime_topology(runtime_config, snapshot, record)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    except Exception as exc:
        console.print(f"[red]Pipeline inspection failed: {exc}[/red]")
        raise typer.Exit(1) from exc

    if not watch:
        if selected_run is None and output_format in {"tree", "edges"}:
            console.print(f"[dim]Configuration: {config_path} · runtime state: configured[/dim]")
        elif selected_run is not None and output_format in {"tree", "edges"}:
            console.print(f"[dim]Run #{selected_run} · {record.get('state', 'unknown')} · config: {config_path or '—'}[/dim]")
        rendered = _render(topology, output_format, run_id=selected_run, snapshot=snapshot)
        if output_format in {"dot", "json"}:
            sys.stdout.write(rendered + "\n")
            sys.stdout.flush()
        else:
            console.print(rendered)
        return

    from rich.live import Live
    stop_message = None
    try:
        with Live(_render(topology, output_format, run_id=selected_run, snapshot=snapshot),
                  console=console, refresh_per_second=4) as live:
            while True:
                time.sleep(1)
                try:
                    runtime_config, record, snapshot = _load_run(int(selected_run))
                except (FileNotFoundError, ValueError) as exc:
                    stop_message = f"Runtime view stopped: {exc}"
                    break
                topology = _runtime_topology(runtime_config, snapshot, record)
                live.update(_render(topology, output_format, run_id=selected_run, snapshot=snapshot))
                if record.get("state") != "running":
                    stop_message = f"Run #{selected_run} is {record.get('state', 'unknown')}; runtime watch stopped."
                    break
    except KeyboardInterrupt:
        return
    except Exception as exc:
        console.print(f"[red]Runtime watch failed: {exc}[/red]")
        raise typer.Exit(1) from exc
    if stop_message:
        console.print(f"[dim]{stop_message}[/dim]")
