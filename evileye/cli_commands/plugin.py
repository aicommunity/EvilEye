"""Commands for scaffolding and inspecting third-party plugin packages."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from evileye.cli_commands.console import console
from evileye.cli_commands.plugin_scaffold import (
    PluginScaffoldError,
    create_plugin_project,
    normalize_plugin_name,
    template_descriptions,
    template_module_id,
)

app = typer.Typer(
    help="Create third-party plugin packages for EvilEye.",
    no_args_is_help=True,
)


@app.command("templates")
def list_templates() -> None:
    """List the available plugin package templates."""
    table = Table(title="EvilEye plugin templates")
    table.add_column("Template", style="cyan")
    table.add_column("What it creates")
    for name, description in template_descriptions().items():
        table.add_row(name, description)
    console.print(table)


@app.command("create")
def create(
    name: str = typer.Argument(..., help="New plugin directory/name, e.g. site-safety"),
    template: str = typer.Option(
        "processor",
        "--template",
        "-t",
        help="Template: processor, detector, alarm, source or pipeline.",
    ),
    output_dir: Path = typer.Option(
        Path("."),
        "--output-dir",
        "-d",
        help="Parent directory for the new plugin folder (default: current directory).",
    ),
) -> None:
    """Create a ready-to-edit plugin package without overwriting existing files."""
    try:
        destination = create_plugin_project(name, output_dir, template)
        _, plugin_id = normalize_plugin_name(name)
    except (PluginScaffoldError, OSError) as exc:
        console.print(f"[red]Plugin scaffold failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(f"[dim]Module identifier: {plugin_id}/{template_module_id(template)}[/dim]")
    console.print(f"[green]Created {template} plugin:[/green] {destination}")
    console.print("[dim]Use the same Python environment as EvilEye; refresh editable-build tooling if needed:[/dim]")
    console.print("  python -m pip install --upgrade pip setuptools")
    console.print(f'  python -m pip install -e "{destination}"')
    console.print("[dim]Then restart EvilEye so it discovers the entry point.[/dim]")
    console.print(f"[dim]Plugin namespace: {plugin_id}/...[/dim]")
