"""`evileye pipeline` commands."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from evileye.cli_commands.console import console

app = typer.Typer(help="Pipeline runtime lifecycle")


@app.command("status")
def pipeline_status() -> None:
    from evileye.stack_control import discover_stack_state

    state = discover_stack_state()
    if not state.console_runs and not state.managed_runs:
        console.print("[dim]No active pipeline runs.[/dim]")
        raise typer.Exit(0)
    table = Table(title="Pipeline runs")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("PID")
    table.add_column("Mode")
    table.add_column("Config")
    for rec in state.console_runs + state.managed_runs:
        mode = "managed" if rec.get("managed") else "direct"
        table.add_row(
            str(rec.get("id", "-")),
            str(rec.get("name", "-")),
            str(rec.get("pid", "-")),
            mode,
            str(rec.get("config_path", "-")),
        )
    console.print(table)


@app.command("stop")
def pipeline_stop(
    config: Optional[str] = typer.Option(None, "--config", help="Stop only this config"),
    all_runs: bool = typer.Option(False, "--all", help="Stop all pipeline runs"),
    hold: bool = typer.Option(False, "--hold", help="Suppress watchdog auto-restart"),
    hold_seconds: int = typer.Option(3600, "--hold-seconds", help="Manual stop cooldown"),
) -> None:
    """Stop pipeline runs. Requires --config or --all."""
    from evileye.stack_control import stop_pipelines

    if not config and not all_runs:
        console.print(
            "[red]Specify --config CONFIG or --all to stop pipelines.[/red]\n"
            "[dim]Example: evileye pipeline stop --all --hold[/dim]"
        )
        raise typer.Exit(1)

    result = stop_pipelines(
        site_dir=Path.cwd(),
        config=config,
        stop_all=all_runs,
        hold=hold,
        hold_seconds=hold_seconds,
    )
    if result.stopped_pids:
        console.print(f"[green]Stopped pipeline PIDs:[/green] {', '.join(str(p) for p in result.stopped_pids)}")
    else:
        console.print("[dim]No running pipeline processes found.[/dim]")
    if result.hold_applied:
        console.print("[yellow]Watchdog manual stop hold applied.[/yellow]")


@app.command("start")
def pipeline_start_cmd(
    config: Optional[str] = typer.Argument(
        None,
        help="Config path/name (optional: uses production_config from site profile)",
    ),
    gui: Optional[bool] = typer.Option(None, "--gui/--no-gui", help="GUI mode for direct launch"),
    detach: bool = typer.Option(False, "--detach", help="Launch in background scope (direct mode)"),
    release: bool = typer.Option(False, "--release", help="Clear watchdog manual stop hold"),
    replace: bool = typer.Option(False, "--replace", help="Stop existing run for this config, then start"),
) -> None:
    """Start pipeline. CONFIG optional when production_config is set in site profile."""
    from evileye.site_runtime_guard import DuplicatePipelineError
    from evileye.stack_control import (
        AmbiguousPipelineConfigError,
        pipeline_start,
        require_pipeline_config,
        should_use_managed_launch,
    )

    try:
        resolved = require_pipeline_config(
            Path.cwd(),
            explicit=config,
            allow_running=False,
        )
        spawn = pipeline_start(
            resolved,
            site_dir=Path.cwd(),
            gui=gui,
            detach=detach,
            release_hold=release,
            replace=replace,
        )
    except AmbiguousPipelineConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    except DuplicatePipelineError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    except Exception as exc:
        console.print(f"[red]Pipeline start failed: {exc}[/red]")
        raise typer.Exit(1)
    mode_hint = "managed" if should_use_managed_launch(Path.cwd()) else "direct"
    console.print(
        f"[green]Pipeline started[/green] mode={spawn.mode} ({mode_hint}) pid={spawn.pid} config={spawn.config_path}"
    )


@app.command("restart")
def pipeline_restart_cmd(
    config: Optional[str] = typer.Argument(
        None,
        help="Config path/name (optional: unique running pipeline or site profile)",
    ),
    gui: Optional[bool] = typer.Option(None, "--gui/--no-gui"),
    detach: bool = typer.Option(True, "--detach/--foreground", help="Detach after restart"),
    hold: bool = typer.Option(True, "--hold/--no-hold", help="Hold watchdog during restart"),
) -> None:
    """Restart pipeline. CONFIG optional when one run is active or profile has production_config."""
    from evileye.stack_control import (
        AmbiguousPipelineConfigError,
        pipeline_restart,
        require_pipeline_config,
    )

    try:
        resolved = require_pipeline_config(
            Path.cwd(),
            explicit=config,
            allow_running=True,
        )
        spawn = pipeline_restart(
            resolved,
            site_dir=Path.cwd(),
            hold=hold,
            gui=gui,
            detach=detach,
        )
    except AmbiguousPipelineConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    except Exception as exc:
        console.print(f"[red]Pipeline restart failed: {exc}[/red]")
        raise typer.Exit(1)
    console.print(
        f"[green]Pipeline restarted[/green] mode={spawn.mode} pid={spawn.pid} config={spawn.config_path}"
    )
