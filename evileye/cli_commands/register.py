"""Register Typer sub-apps on the main EvilEye CLI."""

from __future__ import annotations

import typer

from evileye.cli_commands import dev, pipeline, prod, reload, service, status_cmd, web


def register_stack_commands(app: typer.Typer) -> None:
    app.command("status")(status_cmd.status_cmd)
    app.add_typer(web.app, name="web")
    app.add_typer(service.app, name="service")
    app.add_typer(pipeline.app, name="pipeline")
    app.add_typer(reload.app, name="reload")
    app.add_typer(prod.app, name="prod")
    app.add_typer(dev.app, name="dev")
