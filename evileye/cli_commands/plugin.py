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
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def plugin_root(ctx: typer.Context) -> None:
    from evileye.cli_interactive import handle_group_root

    handle_group_root(ctx, "plugin")


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
    name: str = typer.Argument(None, help="New plugin directory/name, e.g. site-safety"),
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
    if not name:
        from evileye.cli_interactive import (
            InteractiveInputError,
            interactive_available,
            prompt_text,
        )

        if not interactive_available():
            console.print("[red]Plugin name is required.[/red]")
            raise typer.Exit(2)
        try:
            name = prompt_text("Имя нового плагина")
        except InteractiveInputError as exc:
            console.print(f"[yellow]{exc}[/yellow]")
            raise typer.Exit(2) from exc
        if not name:
            raise typer.Exit(2)
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
