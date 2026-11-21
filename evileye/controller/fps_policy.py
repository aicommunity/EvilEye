"""Resolve controller loop FPS for GUI vs headless runs."""

from __future__ import annotations

from typing import Optional

from evileye.gui.gui_mode import GUIMode


def resolve_effective_controller_fps(
    *,
    configured_fps: float,
    gui_mode: GUIMode,
    fps_headless: Optional[float] = None,
) -> float:
    """
    Pick runtime controller.fps.

    - VISIBLE/HIDDEN: keep configured_fps (Qt GUI needs a high feed rate).
    - HEADLESS: use fps_headless when set and > 0; otherwise configured_fps
      (backward compatible).
    """
    configured = float(configured_fps or 0.0)
    if configured <= 0.0:
        configured = 30.0
    if gui_mode == GUIMode.HEADLESS:
        if fps_headless is not None:
            try:
                hl = float(fps_headless)
            except (TypeError, ValueError):
                hl = 0.0
            if hl > 0.0:
                return hl
        return configured
    return configured


def apply_controller_fps_policy(controller_cfg: dict, gui_mode: GUIMode) -> float:
    """
    Mutate controller_cfg in place for a single run.

    Preserves the GUI-oriented value in ``fps_configured`` so config saves do
    not permanently overwrite ``fps`` with the headless effective rate.
    Returns the effective fps applied to ``controller_cfg['fps']``.
    """
    if not isinstance(controller_cfg, dict):
        return 30.0
    if "fps_configured" in controller_cfg:
        try:
            configured = float(controller_cfg.get("fps_configured") or 30.0)
        except (TypeError, ValueError):
            configured = 30.0
    else:
        try:
            configured = float(controller_cfg.get("fps") or 30.0)
        except (TypeError, ValueError):
            configured = 30.0
        controller_cfg["fps_configured"] = configured
    fps_headless = controller_cfg.get("fps_headless")
    effective = resolve_effective_controller_fps(
        configured_fps=configured,
        gui_mode=gui_mode,
        fps_headless=fps_headless,
    )
    controller_cfg["fps"] = effective
    return effective
