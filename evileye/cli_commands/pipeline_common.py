"""Shared helpers for pipeline start/restart CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from evileye.stack_control import SpawnResult


def resolve_and_restart_pipeline(
    *,
    explicit_config: Optional[str],
    site_dir: Path,
    hold: bool,
    detach: bool,
    gui: Optional[bool],
) -> SpawnResult:
    from evileye.stack_control import pipeline_restart, require_pipeline_config

    resolved = require_pipeline_config(
        site_dir,
        explicit=explicit_config,
        allow_running=True,
    )
    return pipeline_restart(
        resolved,
        site_dir=site_dir,
        hold=hold,
        detach=detach,
        gui=gui,
    )
