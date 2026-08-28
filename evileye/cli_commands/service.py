"""`evileye service` commands."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

from evileye.cli_commands.console import console
from evileye.cli_commands.web import ensure_web_environment_for_server as _ensure_web_environment_for_server

app = typer.Typer(help="OS web service install and lifecycle")


@app.command("install")
def service_install(
    config: Optional[Path] = typer.Argument(
        None,
        help="Optional config name/path for auto-run after server start",
    ),
    host: str = typer.Option("0.0.0.0", "--host", help="Bind host for the service"),
    port: int = typer.Option(8181, "--port", help="Bind port for the service"),
    user: bool = typer.Option(False, "--user", help="Force systemd --user unit (Linux)"),
    system: bool = typer.Option(False, "--system", help="Force system unit (may need sudo)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print unit/plan without applying"),
    no_tls: bool = typer.Option(False, "--no-tls", help="Skip HTTPS and keep HTTP"),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Do not prompt; TLS only with explicit flags"),
    tls_self_signed: bool = typer.Option(False, "--tls-self-signed", help="Issue a local mini-CA + leaf certificate"),
    tls_ip: Optional[List[str]] = typer.Option(None, "--tls-ip", help="SAN IP address (repeatable)"),
    tls_dns: Optional[List[str]] = typer.Option(None, "--tls-dns", help="SAN DNS name (repeatable)"),
    ssl_certfile: Optional[str] = typer.Option(None, "--ssl-certfile", help="TLS certificate file (PEM)"),
    ssl_keyfile: Optional[str] = typer.Option(None, "--ssl-keyfile", help="TLS private key file (PEM)"),
    tls_force: bool = typer.Option(False, "--tls-force", help="Overwrite certs/ if files already exist"),
) -> None:
    """Configure HTTPS (optional) and install EvilEye as an OS web service."""
    from evileye.api.core.ssl_files import SslConfigError
    from evileye.service_manager import install_service
    from evileye.service_manager.minimal_config import ensure_system_config
    from evileye.site_profile import save_profile
    from evileye.utils.tls_cert import TlsCertError
    from evileye.utils.tls_deploy_wizard import print_https_hints, run_tls_deploy_step

    site_dir = Path.cwd()
    cfg = str(config) if config is not None else None
    force_user = user or (not system)
    force_system = system
    if user and system:
        console.print("[red]Cannot combine --user and --system[/red]")
        raise typer.Exit(1)

    _ensure_web_environment_for_server()
    ensure_system_config(site_dir)
    try:
        tls_result = run_tls_deploy_step(
            site_dir=site_dir,
            console=console,
            no_tls=no_tls,
            non_interactive=non_interactive,
            tls_self_signed=tls_self_signed,
            tls_ips=tls_ip or [],
            tls_dns=tls_dns or [],
            ssl_certfile=ssl_certfile,
            ssl_keyfile=ssl_keyfile,
            tls_force=tls_force,
        )
    except (TlsCertError, SslConfigError) as exc:
        console.print(f"[red]HTTPS setup failed: {exc}[/red]")
        raise typer.Exit(1)
    print_https_hints(console, tls_result)

    try:
        result = install_service(
            site_dir=site_dir,
            config=cfg,
            host=host,
            port=port,
            force_user=force_user and not force_system,
            force_system=force_system,
            dry_run=dry_run,
            ssl_certfile=ssl_certfile,
            ssl_keyfile=ssl_keyfile,
        )
    except Exception as e:
        console.print(f"[red]service install failed: {e}[/red]")
        raise typer.Exit(1)

    if dry_run and result.unit_text:
        console.print("[blue]Dry-run unit file:[/blue]")
        console.print(result.unit_text)

    if result.ok and not dry_run:
        save_profile(
            {
                "version": 2,
                "production_config": cfg,
                "watchdog_config": cfg,
                "pipeline_launch": "auto",
                "gui_default": False,
                "port": port,
                "host": host,
            },
            site_dir,
        )

    if result.ok:
        console.print(f"[green]{result.message}[/green]")
    else:
        style = "yellow" if result.warn_only else "red"
        console.print(f"[{style}]{result.message}[/{style}]")
        if not result.warn_only:
            raise typer.Exit(1)


@app.command("uninstall")
def service_uninstall(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be removed"),
) -> None:
    """Stop and remove the EvilEye OS web service."""
    from evileye.service_manager import uninstall_service

    try:
        result = uninstall_service(site_dir=Path.cwd(), dry_run=dry_run)
    except Exception as e:
        console.print(f"[red]service uninstall failed: {e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]{result.message}[/green]")


@app.command("start")
def service_start() -> None:
    from evileye.service_manager import control_service

    result = control_service("start", site_dir=Path.cwd())
    if result.ok:
        console.print(f"[green]{result.message}[/green]")
    else:
        console.print(f"[red]{result.message}[/red]")
        raise typer.Exit(1)


@app.command("stop")
def service_stop() -> None:
    from evileye.service_manager import control_service

    result = control_service("stop", site_dir=Path.cwd())
    if result.ok:
        console.print(f"[green]{result.message}[/green]")
    else:
        console.print(f"[red]{result.message}[/red]")
        raise typer.Exit(1)


@app.command("restart")
def service_restart() -> None:
    from evileye.service_manager import control_service
    from evileye.stack_control import wait_web_ready
    from evileye.site_profile import service_port

    result = control_service("restart", site_dir=Path.cwd())
    port = service_port(Path.cwd())
    ready = wait_web_ready(port=port, timeout=60.0) if result.ok else False
    if result.ok and ready:
        console.print(f"[green]{result.message}[/green]")
    elif result.ok:
        console.print(f"[yellow]{result.message} (but /ready not responding yet)[/yellow]")
    else:
        console.print(f"[red]{result.message}[/red]")
        raise typer.Exit(1)


@app.command("status")
def service_status() -> None:
    from evileye.service_manager import control_service

    result = control_service("status", site_dir=Path.cwd())
    console.print(result.message)
    raise typer.Exit(0 if result.ok else 1)
