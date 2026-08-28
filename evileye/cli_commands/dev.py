"""`evileye dev` commands."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import typer

from evileye.cli_commands.console import console

app = typer.Typer(help="Development workflows")


@app.callback(invoke_without_command=True)
def dev_root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        console.print("Usage: evileye dev server")
        raise typer.Exit(2)


@app.command("server")
def dev_server(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8181, "--port"),
    verbose: bool = typer.Option(False, "--verbose"),
    log_level: str = typer.Option("info", "--log-level"),
) -> None:
    """Run foreground web server (no systemd)."""
    from evileye.service_manager import is_web_os_service_active

    if is_web_os_service_active():
        console.print(
            "[yellow]OS web service is active. Stop it first: evileye service stop[/yellow]"
        )
        raise typer.Exit(1)

    cmd = [sys.executable, str(Path(__file__).resolve().parents[1] / "server.py")]
    cmd.extend(["--host", host, "--port", str(port), "--log-level", log_level, "--no-reload"])
    if verbose:
        cmd.append("--verbose")
    console.print(f"[green]Starting dev server on http://{host}:{port}[/green]")
    try:
        subprocess.run(cmd, check=True, cwd=os.getcwd())
    except KeyboardInterrupt:
        raise typer.Exit(0)
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]Server failed: {exc}[/red]")
        raise typer.Exit(1)
