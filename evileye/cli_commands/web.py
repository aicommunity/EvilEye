"""`evileye web` commands."""

from __future__ import annotations

from typing import Optional

import typer
from rich.table import Table

from evileye.cli_commands.console import console

app = typer.Typer(help="Web UI build and dependency management")


def _print_web_setup_failures(report) -> None:
    for item in report.items:
        if item.ok:
            continue
        if item.name == "python:turbojpeg_native":
            continue
        console.print(f"[yellow]  {item.name}:[/yellow] {item.detail}")


def _print_ensure_web_result(result) -> None:
    from evileye import setup_web as sw

    if result.error:
        console.print(f"[red]Web UI setup failed: {result.error}[/red]")
    if result.opencv_preview:
        console.print(f"[yellow]{sw.LIBTURBOJPEG_HINT}[/yellow]")
        console.print("[yellow]Preview will use OpenCV fallback until libturbojpeg is installed.[/yellow]")
    if result.ready:
        console.print("[green]Web UI environment is ready.[/green]")
        return
    _print_web_setup_failures(result.report)
    console.print("[red]Web UI setup incomplete.[/red]")


def ensure_web_environment_for_server() -> None:
    """If Web UI deps/SPA are missing, install them before service install."""
    _ensure_web_environment_for_server_impl()


def _ensure_web_environment_for_server_impl() -> None:
    from evileye import setup_web as sw

    report = sw.collect_web_setup_report()
    if report.can_serve_ui():
        if report.needs_libturbojpeg():
            console.print(f"[yellow]{sw.LIBTURBOJPEG_HINT}[/yellow]")
        return
    console.print("[yellow]Web UI environment is not ready. Running web deps/build…[/yellow]")
    _print_web_setup_failures(report)
    result = sw.ensure_web_environment(scope="user", log=lambda msg: console.print(f"[blue]{msg}[/blue]"))
    _print_ensure_web_result(result)
    if not result.ready:
        raise typer.Exit(1)
    console.print("[green]Web UI environment check passed; continuing with service install.[/green]")


@app.command("check")
def web_check() -> None:
    """Verify Web UI Python deps and SPA static files."""
    from evileye import setup_web as sw

    report = sw.collect_web_setup_report()
    table = Table(title="EvilEye Web UI environment")
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Detail")
    for item in report.items:
        status = "[green]OK[/green]" if item.ok else "[red]FAIL[/red]"
        table.add_row(item.name, status, item.detail)
    console.print(table)
    if report.ok:
        console.print("[green]Web UI environment looks ready.[/green]")
        raise typer.Exit(0)
    if report.needs_libturbojpeg():
        console.print(f"[yellow]{sw.LIBTURBOJPEG_HINT}[/yellow]")
    raise typer.Exit(1)


@app.command("deps")
def web_deps(
    scope: str = typer.Option(
        "user",
        "--scope",
        help="pip scope: user (~/.local) or system (sudo pip)",
        case_sensitive=False,
    ),
    force: bool = typer.Option(False, "--force", help="Reinstall missing Python packages"),
) -> None:
    """Install missing Python API packages."""
    from evileye import setup_web as sw

    scope_norm = (scope or "user").strip().lower()
    if scope_norm not in {"user", "system"}:
        console.print("[red]--scope must be 'user' or 'system'[/red]")
        raise typer.Exit(1)
    if scope_norm == "system":
        if not typer.confirm("Install missing Python packages system-wide with sudo?", default=False):
            raise typer.Exit(1)
    result = sw.ensure_web_environment(
        scope=scope_norm,
        force=force,
        build=False,
        log=lambda msg: console.print(f"[blue]{msg}[/blue]"),
    )
    _print_ensure_web_result(result)
    raise typer.Exit(0 if result.ready else 1)


@app.command("build")
def web_build(force: bool = typer.Option(False, "--force", help="Force npm rebuild")) -> None:
    """Build SPA into evileye/api/static/."""
    from evileye import setup_web as sw
    from evileye.stack_control import frontend_needs_build

    if not force and not frontend_needs_build():
        report = sw.collect_web_setup_report()
        if report.can_serve_ui():
            console.print("[green]SPA static is up to date.[/green]")
            raise typer.Exit(0)
    try:
        sw.build_frontend()
    except Exception as exc:
        console.print(f"[red]Build failed: {exc}[/red]")
        raise typer.Exit(1)
    console.print("[green]Frontend build completed.[/green]")


@app.command("refresh")
def web_refresh(
    force: bool = typer.Option(False, "--force", help="Force SPA rebuild before service restart"),
) -> None:
    """Rebuild SPA if needed and restart the OS web service."""
    from evileye.stack_control import ContainerOperationError, restart_web_layer

    try:
        restart_web_layer(force_build=force, log=lambda msg: console.print(f"[blue]{msg}[/blue]"))
    except ContainerOperationError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(1)
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)
    console.print("[green]Web layer refreshed.[/green]")
