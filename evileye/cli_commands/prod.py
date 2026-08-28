"""`evileye prod` commands."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

from evileye.cli_commands.console import console

app = typer.Typer(help="Production site bootstrap and operations")


@app.callback(invoke_without_command=True)
def prod_root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        console.print("Usage: evileye prod [init|up|down|restart]")
        raise typer.Exit(2)


@app.command("init")
def prod_init(
    config: Path = typer.Argument(..., help="Production config path"),
    install_watchdog: bool = typer.Option(True, "--watchdog/--no-watchdog"),
) -> None:
    """Deploy site files, install web service, optional watchdog, save profile."""
    from evileye.site_profile import save_profile
    from evileye.watchdog_native import install_watchdog

    site_dir = Path.cwd()
    subprocess.run([sys.executable, "-m", "evileye.cli_wrapper", "deploy"], check=True, cwd=str(site_dir))
    subprocess.run(
        [sys.executable, "-m", "evileye.cli_wrapper", "service", "install", str(config)],
        check=True,
        cwd=str(site_dir),
    )
    cfg = str(config)
    save_profile(
        {
            "version": 2,
            "production_config": cfg,
            "watchdog_config": cfg,
            "pipeline_launch": "auto",
            "gui_default": False,
        },
        site_dir,
    )
    if install_watchdog:
        try:
            install_watchdog(config=cfg, root=site_dir)
            console.print("[green]Watchdog installed.[/green]")
        except Exception as exc:
            console.print(f"[yellow]Watchdog install skipped: {exc}[/yellow]")
    console.print("[green]Production site initialized.[/green]")


@app.command("up")
def prod_up() -> None:
    from evileye.service_manager import control_service, is_service_installed
    from evileye.site_profile import resolve_production_config, service_port
    from evileye.stack_control import pipeline_start, wait_web_ready

    site_dir = Path.cwd()
    cfg = resolve_production_config(site_dir)
    if is_service_installed(site_dir):
        result = control_service("start", site_dir=site_dir)
        if not result.ok:
            console.print(f"[red]{result.message}[/red]")
            raise typer.Exit(1)
        if not wait_web_ready(port=service_port(site_dir), timeout=60.0):
            console.print("[red]Web service did not become ready.[/red]")
            raise typer.Exit(1)
    if not cfg:
        console.print("[yellow]No production_config in site profile; web service only.[/yellow]")
        raise typer.Exit(0)
    spawn = pipeline_start(cfg, site_dir=site_dir, detach=True, release_hold=True, gui=False)
    console.print(f"[green]Production stack up[/green] pipeline pid={spawn.pid} mode={spawn.mode}")


@app.command("down")
def prod_down(
    stop_service: bool = typer.Option(False, "--stop-service", help="Also stop OS web service"),
) -> None:
    from evileye.service_manager import control_service, is_service_installed
    from evileye.stack_control import stop_pipelines

    site_dir = Path.cwd()
    stop_pipelines(site_dir=site_dir, stop_all=True, hold=True)
    if stop_service and is_service_installed(site_dir):
        control_service("stop", site_dir=site_dir)
    console.print("[green]Production stack stopped (watchdog hold active).[/green]")


@app.command("restart")
def prod_restart(
    with_pipeline: bool = typer.Option(True, "--with-pipeline/--web-only"),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    from evileye.site_profile import resolve_production_config
    from evileye.stack_control import reload_web

    cfg = str(config) if config else resolve_production_config(Path.cwd())
    result = reload_web(
        site_dir=Path.cwd(),
        with_pipeline=with_pipeline,
        config=cfg,
        release_hold=True,
        log=lambda msg: console.print(f"[blue]{msg}[/blue]"),
    )
    if result.ok:
        console.print(f"[green]{result.message}[/green]")
    else:
        console.print(f"[red]{result.message}[/red]")
        raise typer.Exit(1)
