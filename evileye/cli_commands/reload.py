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
    release: bool = typer.Option(
        True,
        "--release/--no-release",
        help="Clear watchdog manual stop hold after pipeline start (default: clear)",
    ),
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
    config: Optional[str] = typer.Argument(
        None,
        help="Config path/name (optional: unique running pipeline or site profile)",
    ),
    detach: bool = typer.Option(
        True,
        "--detach/--foreground",
        help="Detach after restart (default). --foreground waits for pipeline exit.",
    ),
    hold: bool = typer.Option(
        True,
        "--hold/--no-hold",
        help="Set restart grace during stop/start (not a 1h manual stop). Default: on.",
    ),
    gui: Optional[bool] = typer.Option(None, "--gui/--no-gui"),
) -> None:
    """Restart pipeline only (alias of `evileye pipeline restart`)."""
    from evileye.cli_commands.pipeline_common import resolve_and_restart_pipeline
    from evileye.stack_control import AmbiguousPipelineConfigError

    try:
        spawn = resolve_and_restart_pipeline(
            explicit_config=config,
            site_dir=Path.cwd(),
            hold=hold,
            detach=detach,
            gui=gui,
        )
    except AmbiguousPipelineConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    if spawn.mode == "direct-foreground":
        code = 0 if spawn.exit_code is None else int(spawn.exit_code)
        raise typer.Exit(code)

    console.print(
        f"[green]Pipeline reloaded[/green] pid={spawn.pid} mode={spawn.mode} config={spawn.config_path}"
    )
