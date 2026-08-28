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
    from evileye.site_runtime_guard import DuplicateWebError, ensure_web_singleton, spawn_lock

    site = Path.cwd().resolve()
    try:
        with spawn_lock(site):
            ensure_web_singleton(site, policy="fail", port=port)
    except DuplicateWebError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    cmd = [sys.executable, str(Path(__file__).resolve().parents[1] / "server.py")]
    cmd.extend(["--host", host, "--port", str(port), "--log-level", log_level, "--no-reload"])
    if verbose:
        cmd.append("--verbose")
    console.print(f"[green]Starting dev server on http://{host}:{port}[/green]")
    env = os.environ.copy()
    env["EVILEYE_SITE_DIR"] = str(site)
    try:
        subprocess.run(cmd, check=True, cwd=os.getcwd(), env=env)
    except KeyboardInterrupt:
        raise typer.Exit(0)
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]Server failed: {exc}[/red]")
        raise typer.Exit(1)
