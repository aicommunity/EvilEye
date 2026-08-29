"""`evileye status` command."""

from __future__ import annotations

import json

import typer
from rich.table import Table

from evileye.cli_commands.console import console
from evileye.stack_control import discover_stack_state, stack_state_to_json


def status_cmd(
    as_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output"),
) -> None:
    """Show unified EvilEye stack status."""
    state = discover_stack_state()
    if as_json:
        console.print(json.dumps(stack_state_to_json(state), indent=2, default=str))
        raise typer.Exit(0)

    table = Table(title="EvilEye stack status")
    table.add_column("Component", style="cyan")
    table.add_column("Value")
    table.add_row("Site", str(state.site_dir))
    table.add_row("Container", "yes" if state.in_container else "no")
    table.add_row("OS service", "installed" if state.service_installed else "not installed")
    table.add_row("Service backend", state.service_backend or "-")
    table.add_row("Service enabled", "yes" if state.service_enabled else "no")
    table.add_row("Service active", "yes" if state.service_active else "no")
    table.add_row("Port", f"{state.port} ({state.port_scheme})")
    table.add_row("Port listener PID", str(state.port_listener_pid or "-"))
    table.add_row("Foreground server PIDs", ", ".join(str(p) for p in state.foreground_server_pids) or "-")
    table.add_row("Console pipelines", str(len(state.console_runs)))
    table.add_row("Managed pipelines", str(len(state.managed_runs)))
    table.add_row("Watchdog config", state.watchdog_config or "-")
    table.add_row("Watchdog grace", "active" if state.watchdog_grace_active else "no")
    table.add_row("Manual stop hold", "active" if state.manual_stop_active else "no")
    console.print(table)

    if state.console_runs or state.managed_runs:
        runs = Table(title="Active pipeline runs")
        runs.add_column("ID")
        runs.add_column("Name")
        runs.add_column("PID")
        runs.add_column("Managed")
        runs.add_column("Config")
        for rec in state.console_runs + state.managed_runs:
            runs.add_row(
                str(rec.get("id", "-")),
                str(rec.get("name", "-")),
                str(rec.get("pid", "-")),
                "yes" if rec.get("managed") else "no",
                str(rec.get("config_path", "-")),
            )
        console.print(runs)

    for warning in state.warnings:
        console.print(f"[yellow]Warning:[/yellow] {warning}")
    if state.suggested_command:
        console.print(f"[dim]Suggested:[/dim] {state.suggested_command}")
