"""`evileye reload` commands."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from evileye.cli_commands.console import console

app = typer.Typer(help="Ordered stack reload operations")


@app.callback(invoke_without_command=True)
def reload_root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        console.print("Usage: evileye reload [web|backend|pipeline]")
        raise typer.Exit(2)


@app.command("web")
def reload_web_cmd(
    force_build: bool = typer.Option(False, "--force-build", help="Force SPA rebuild"),
    with_pipeline: bool = typer.Option(False, "--with-pipeline", help="Restart pipeline after web reload"),
    config: Optional[str] = typer.Option(None, "--config", help="Pipeline config for restart"),
    release: bool = typer.Option(True, "--release/--no-release", help="Clear watchdog hold after pipeline start"),
) -> None:
    from evileye.stack_control import reload_web

    result = reload_web(
        site_dir=Path.cwd(),
        force_build=force_build,
        with_pipeline=with_pipeline,
        config=config,
        release_hold=release,
        log=lambda msg: console.print(f"[blue]{msg}[/blue]"),
    )
    if result.ok:
        console.print(f"[green]{result.message}[/green]")
        if result.details:
            console.print(f"[dim]{result.details}[/dim]")
    else:
        console.print(f"[red]{result.message}[/red]")
        raise typer.Exit(1)


@app.command("backend")
def reload_backend_cmd() -> None:
    from evileye.stack_control import reload_backend

    result = reload_backend(site_dir=Path.cwd())
    if result.ok:
        console.print(f"[green]{result.message}[/green]")
    else:
        console.print(f"[red]{result.message}[/red]")
        raise typer.Exit(1)


@app.command("pipeline")
def reload_pipeline_cmd(
    config: str = typer.Argument(..., help="Configuration file path or name"),
    detach: bool = typer.Option(True, "--detach/--foreground"),
) -> None:
    from evileye.stack_control import pipeline_restart

    try:
        spawn = pipeline_restart(config, site_dir=Path.cwd(), hold=True, detach=detach)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Pipeline reloaded[/green] pid={spawn.pid} mode={spawn.mode}")
